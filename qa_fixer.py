import pandas as pd
import re

# 1) CSV 불러오기 (한글이라 cp949 가능성이 큼)
raw_path = "(ESTSoft)+바이브+코딩+인턴+샘플+Q_A+데이터+1.csv"
df = pd.read_csv(raw_path, encoding="cp949")

# 우리가 쓸 컬럼 이름
col_text = "Unnamed: 2"   # Q./A.가 들어 있는 컬럼
col_num  = "Unnamed: 1"   # 순번이 들어있는 컬럼

rows = []

for idx, row in df.iterrows():
    text = str(row.get(col_text, ""))
    # Q. 로 시작하는 행만 찾기
    if text.startswith("Q."):
        q_text = text

        # 바로 다음 행이 답변(A.)라고 가정
        if idx + 1 < len(df):
            next_text = str(df.loc[idx + 1, col_text])
        else:
            next_text = ""

        if not next_text.startswith("A."):
            # 데이터가 깨져 있으면 스킵
            continue

        a_text = next_text

        # 앞의 'Q. ', 'A. ' 제거 + 양끝 공백 정리
        q_clean = re.sub(r"^Q\.\s*", "", q_text).strip()
        a_clean = re.sub(r"^A\.\s*", "", a_text).strip()

        # 순번(번호) 가져오기 – 없으면 None
        num_val = row.get(col_num, None)
        if pd.notna(num_val):
            try:
                num_int = int(num_val)
            except:
                num_int = None
        else:
            num_int = None

        # id 만들기 (순번 기준이 있으면 그걸 쓰고, 없으면 row 개수 기준)
        if num_int is not None:
            qa_id = f"QA_{num_int:03d}"
        else:
            qa_id = f"QA_{len(rows)+1:03d}"

        rows.append({
            "id": qa_id,
            "num": num_int,
            "question": q_clean,
            "answer": a_clean,
        })

# DataFrame으로 변환
qa_df = pd.DataFrame(rows)

def rule_category(q: str) -> str:
    # 매우 단순한 키워드 기반 분류
    if any(k in q for k in ["요금제", "요금", "가격"]):
        return "pricing"
    elif "언어" in q:
        return "language"
    elif "기능" in q:
        return "feature"
    elif any(k in q for k in ["어떤 서비스", "어떤 회사"]):
        return "overview"
    elif any(k in q for k in ["고객센터", "문의"]):
        return "support"
    else:
        return "general"

qa_df["category"] = qa_df["question"].apply(rule_category)

qa_df.to_csv("qa_clean_with_category.csv", index=False, encoding="utf-8-sig")

print(qa_df.head())
print("총 Q&A 개수:", len(qa_df))

# 정제된 CSV로 저장
qa_df.to_csv("qa_clean.csv", index=False, encoding="utf-8-sig")
