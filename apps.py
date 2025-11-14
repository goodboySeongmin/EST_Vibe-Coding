# app.py
import os
from typing import Optional, List
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openai import OpenAI
from pinecone import Pinecone

from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal
from models import ChatLog


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


# 3-A) 질문 리라이트 함수 (LLM을 이용해 FAQ 스타일 질문으로 바꾸기)
def rewrite_query(user_message: str) -> str:
    """
    사용자의 자연어 질문을 Perso.ai FAQ에 어울리는
    "완전한 한 문장 질문"으로 다듬는다.
    - 새로운 사실/숫자/연락처/URL 등을 추가하지 않는다.
    - 응답은 오직 질문 한 문장만.
    """
    if not user_message or len(user_message.strip()) < 2:
        return user_message

    system_prompt = """
너는 FAQ 검색을 위한 "질문 리라이터"야.

- 사용자가 한 말을, Perso.ai FAQ에 있을 법한 "완전한 한 문장 질문"으로 바꿔.
- 새 사실, 숫자, 이메일, URL, 전화번호, 기능 등을 절대 추가하지 마.
- 서비스 이름(Perso.ai)처럼 문맥상 당연한 것만 보완해도 돼.
- 예시:
  - "고객센터에 연결해줘" -> "Perso.ai 고객센터는 어떻게 문의하나요?"
  - "요금 알려줘" -> "Perso.ai 요금제는 어떻게 구성되어 있나요?"
- 답변을 만들지 말고, 오직 "질문 한 문장"만 내보내.
"""

    try:
        res = openai_client.chat.completions.create(
            model="gpt-4.1-mini",  # 또는 사용 가능한 경량 모델
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,  # 창의성 최소화 → 할루시네이션 최소화
        )
        rewritten = (res.choices[0].message.content or "").strip()
        if not rewritten or len(rewritten) < 3:
            return user_message
        return rewritten
    except Exception as e:
        # 리라이트 단계에서 에러가 나도 전체 서비스는 계속 동작하도록
        print("rewrite_query error:", e)
        return user_message


# 4) Q&A 검색 함수
def search_qa(
    user_query: str,
    top_k: int = 3,
    score_threshold: float = 0.55,
):
    """
    주어진 문장(user_query)을 임베딩하여 Pinecone에서
    가장 유사한 FAQ를 검색한 뒤, best match를 반환한다.
    """
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
    사용자 질문을 받아서
    1) LLM으로 FAQ 스타일로 리라이트한 뒤
    2) 리라이트된 문장으로 Pinecone에서 가장 유사한 Q&A를 찾고,
    3) answer를 그대로 반환하며, 질문/답변을 DB에 기록한다.
    """
    raw_question = req.message.strip()

    # 1) 질문 리라이트
    rewritten = rewrite_query(raw_question)

    # 2) 리라이트된 질문으로 검색
    result = search_qa(rewritten)

    # 기본값 세팅
    found = False
    answer = "제공된 Q&A 데이터에서 적절한 답변을 찾지 못했습니다."
    source_q = None
    score = None

    if result is not None:
        source_q = result.get("question")
        score = result.get("score")
        if result.get("found"):
            found = True
            answer = result.get("answer", answer)

    # DB에 한 줄 기록 (사용자 원본 질문을 저장)
    log = ChatLog(
        question=raw_question,
        answer=answer,
        source_question=source_q,
        score=score,
    )
    db.add(log)
    db.commit()

    # 프론트로 응답
    return ChatResponse(
        found=found,
        answer=answer,
        source_question=source_q,
        score=score,
    )


# 9) 로그 조회용 모델/엔드포인트
class ChatLogOut(BaseModel):
    id: int
    question: str
    answer: str
    source_question: str | None = None
    score: float | None = None
    created_at: datetime  # 실제 DB 타입과 맞추기

    class Config:
        orm_mode = True  # 또는 from_attributes = True 여도 괜찮음


@app.get("/logs", response_model=List[ChatLogOut])
def get_logs(db: Session = Depends(get_db)):
    logs = db.query(ChatLog).order_by(ChatLog.created_at.desc()).limit(50).all()
    return logs
