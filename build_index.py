import os
import time
import pandas as pd
from dotenv import load_dotenv

from openai import OpenAI
from pinecone import Pinecone

# ============================
# 1) 환경변수 로드
# ============================
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_HOST = os.getenv("PINECONE_INDEX_HOST")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY가 .env에 설정되어 있지 않습니다.")
if not PINECONE_API_KEY or not PINECONE_INDEX_HOST:
    raise ValueError("PINECONE_API_KEY 또는 PINECONE_INDEX_HOST가 설정되어 있지 않습니다.")

# ============================
# 2) 클라이언트 초기화
# ============================
openai_client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(host=PINECONE_INDEX_HOST)

NAMESPACE = "default"

# ============================
# 3) CSV 로드
# ============================
csv_path = "qa_clean.csv"   # 경로 다르면 수정
df = pd.read_csv(csv_path)

# category 컬럼이 없을 수도 있으니 대비
has_category = "category" in df.columns

print(f"✅ CSV 로드 완료: {len(df)} rows")
print(f"   columns: {list(df.columns)}")

# ============================
# 4) 기존 namespace 삭제 (선택)
# ============================
CLEAR_BEFORE_INSERT = True  # 기존 벡터 싹 지우고 새로 넣고 싶으면 True

if CLEAR_BEFORE_INSERT:
    print(f"🧹 기존 namespace('{NAMESPACE}') 전체 삭제 중...")
    # host 기반 클라이언트에서는 delete_all=True 사용
    index.delete(namespace=NAMESPACE, delete_all=True)
    print("   → 삭제 완료")

# ============================
# 5) 임베딩 함수
# ============================
def embed_text(text: str) -> list:
    """
    OpenAI text-embedding-3-small로 임베딩 생성
    """
    resp = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return resp.data[0].embedding

# ============================
# 6) 배치 업서트
# ============================
batch_size = 32
vectors = []

for i, row in df.iterrows():
    # id 컬럼이 없을 수도 있으니 대비
    if "id" in df.columns:
        qa_id = str(row["id"])
    else:
        # 없으면 index 기반으로 생성
        qa_id = str(i)

    question = str(row["question"])
    answer = str(row["answer"])

    # ✅ 임베딩에 넣을 내용: Q + A를 합쳐서 하나의 의미 덩어리로
    #    이렇게 해야 "이스트소프트는 어떤 기업이야?" 같이
    #    답변에만 있는 키워드도 잘 잡힌다.
    content = f"Q: {question}\nA: {answer}"

    emb = embed_text(content)

    metadata = {
        "id": qa_id,
        "question": question,
        "answer": answer,
    }
    if has_category:
        metadata["category"] = str(row["category"])

    vectors.append(
        {
            "id": qa_id,
            "values": emb,
            "metadata": metadata,
        }
    )

    # 배치마다 업서트
    if len(vectors) >= batch_size:
        print(f"📤 Upserting {len(vectors)} vectors ... (i={i})")
        index.upsert(vectors=vectors, namespace=NAMESPACE)
        vectors = []
        # 너무 빠르면 레이트 리밋 걸릴 수도 있으니 살짝 쉬어주기
        time.sleep(0.2)

# 마지막 남은 벡터들 업서트
if vectors:
    print(f"📤 Upserting last {len(vectors)} vectors ...")
    index.upsert(vectors=vectors, namespace=NAMESPACE)

print("✅ Pinecone 인덱스 업서트 완료!")
