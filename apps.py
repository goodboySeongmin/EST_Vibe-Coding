# app.py
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openai import OpenAI
from pinecone import Pinecone

from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal
from models import ChatLog
from datetime import datetime


# 1) 환경변수 로드
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_HOST = os.getenv("PINECONE_INDEX_HOST")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY가 .env에 설정되어 있지 않습니다.")
if not PINECONE_API_KEY or not PINECONE_INDEX_HOST:
    raise ValueError("PINECONE_API_KEY 또는 PINECONE_INDEX_HOST가 설정되어 있지 않습니다.")

# 2) 클라이언트 초기화
openai_client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(host=PINECONE_INDEX_HOST)

NAMESPACE = "default"   # build_index.py에서 사용한 namespace와 동일해야 함

# 3) 임베딩 함수
def embed_text(text: str) -> list:
    resp = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return resp.data[0].embedding

# 4) Q&A 검색 함수
def search_qa(
    user_query: str,
    top_k: int = 3,
    score_threshold: float = 0.7,
):
    query_emb = embed_text(user_query)

    res = index.query(
        namespace=NAMESPACE,
        vector=query_emb,
        top_k=top_k,
        include_metadata=True,
        include_values=False,
    )

    matches = res.get("matches", []) or res.get("data", [])
    if not matches:
        return None

    matches = sorted(matches, key=lambda m: m["score"], reverse=True)
    best = matches[0]

    data = {
        "found": best["score"] >= score_threshold,
        "score": float(best["score"]),
        "question": best["metadata"].get("question"),
        "answer": best["metadata"].get("answer"),
    }

    # 디버깅용으로 top_k 전체도 보고 싶으면 여기에 matches를 같이 넣어도 됨
    return data

# 5) FastAPI 앱 정의
app = FastAPI(
    title="VibeCoding Q&A Chatbot API",
    description="CSV 기반 Q&A + Pinecone 검색 API",
    version="0.1.0",
)

# 앱 뜰 때 테이블 자동 생성
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# CORS (나중에 웹 프론트 연결할 때 편하게 하려고 열어둠)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 배포할 땐 특정 도메인만 허용하는 게 좋음
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 6) 요청/응답 모델 정의
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    found: bool
    answer: str
    source_question: Optional[str] = None
    score: Optional[float] = None

# 7) 헬스체크
@app.get("/health")
def health_check():
    return {"status": "ok"}


# 8) 메인 채팅 엔드포인트
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """
    사용자 질문을 받아서 Pinecone에서 가장 유사한 Q&A를 찾아,
    answer를 그대로 반환하고, 질문/답변을 DB에 기록한다.
    """
    result = search_qa(req.message)

    # 기본값 세팅
    found = False
    answer = "제공된 Q&A 데이터에서 적절한 답변을 찾지 못했습니다."
    source_q = None
    score = None

    if result is not None:
        source_q = result.get("question")
        score = result.get("score")

        if result.get("found"):
            # 유사도 기준을 통과했을 때
            found = True
            answer = result.get("answer", answer)

    # 🔹 여기서 DB에 한 줄 기록
    log = ChatLog(
        question=req.message,
        answer=answer,
        source_question=source_q,
        score=score,
    )
    db.add(log)
    db.commit()

    # 🔹 프론트로 응답
    return ChatResponse(
        found=found,
        answer=answer,
        source_question=source_q,
        score=score,
    )



from typing import List

class ChatLogOut(BaseModel):
    id: int
    question: str
    answer: str
    source_question: str | None = None
    score: float | None = None
    created_at: datetime  # ✅ 실제 DB 타입과 맞추기

    class Config:
        orm_mode = True  # (또는 from_attributes = True 여도 괜찮음)



@app.get("/logs", response_model=List[ChatLogOut])
def get_logs(db: Session = Depends(get_db)):
    logs = db.query(ChatLog).order_by(ChatLog.created_at.desc()).limit(50).all()
    return logs

