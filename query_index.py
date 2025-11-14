import os
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

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
index = pc.Index(host=PINECONE_INDEX_HOST)  # build_index.py와 동일하게!

NAMESPACE = "default"   # build_index.py에서 upsert할 때 쓴 namespace 그대로

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
    score_threshold: float = 0.6
):
    """
    사용자 질문을 임베딩해서 Pinecone에서 유사한 Q&A를 찾는다.
    score_threshold보다 낮으면 "없음" 처리.
    """
    query_emb = embed_text(user_query)

    res = index.query(
        namespace=NAMESPACE,
        vector=query_emb,
        top_k=top_k,
        include_metadata=True,
        include_values=False
    )

    matches = res.get("matches", []) or res.get("data", [])  # SDK 버전에 따라 다를 수 있어 대비

    if not matches:
        return None

    # 점수 순으로 정렬 (혹시나 정렬이 안 돼서 오는 경우 대비)
    matches = sorted(matches, key=lambda m: m["score"], reverse=True)
    best = matches[0]

    if best["score"] < score_threshold:
        # 유사도 낮으면 "데이터에 없다"로 처리
        return {
            "found": False,
            "score": best["score"],
            "question": best["metadata"].get("question"),
            "answer": best["metadata"].get("answer"),
        }

    return {
        "found": True,
        "score": best["score"],
        "question": best["metadata"].get("question"),
        "answer": best["metadata"].get("answer"),
        "raw_matches": matches,  # 필요하면 디버깅용으로 전체도 같이 반환
    }

if __name__ == "__main__":
    print("=== VibeCoding Q&A 검색 테스트 ===")
    while True:
        query = input("\n질문을 입력하세요 (종료: q): ").strip()
        if query.lower() == "q":
            break

        result = search_qa(query)

        if result is None or not result["found"]:
            print("➡️  제공된 Q&A 데이터에서 적절한 답변을 찾지 못했습니다.")
            if result is not None:
                print(f"   (가장 가까운 유사도: {result['score']:.3f})")
        else:
            print(f"\n[매칭 유사도] {result['score']:.3f}")
            print(f"[원본 질문] {result['question']}")
            print(f"[답변]\n{result['answer']}")
