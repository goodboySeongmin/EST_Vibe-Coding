# Perso.ai FAQ 기반 고객지원 챗봇

Perso.ai의 **벡터 DB 기반 FAQ 챗봇**입니다.  
제공된 Q&A 데이터셋만을 사용해, **할루시네이션 없이 정확한 답변**을 반환하는 것을 목표로 합니다.

[Perso.ai Support](https://perso-support.vercel.app/)
---

## 1. 프로젝트 개요

- **목표**
  - Perso.ai FAQ Q&A 데이터(xlsx → csv)를 기반으로
  - 사용자가 질문했을 때 **데이터셋에 존재하는 답변만** 반환
  - ChatGPT / Claude와 유사한 **웹 UI + 실제 배포**까지 구현

- **핵심 특징**
  - Vector DB(Pinecone) + OpenAI 임베딩으로 **유사도 기반 검색**
  - LLM은 **질문 리라이트 전용**으로만 사용 → 최종 답변은 항상 FAQ 데이터에서만
  - Threshold 기반 필터링으로 **애매한 질문은 “모르겠습니다” 처리**

---

## 2. 사용 기술 스택

### 2.1 백엔드

- **언어 & 프레임워크**
  - Python 3 + **FastAPI**
- **AI / Vector**
  - OpenAI
    - `text-embedding-3-small` : FAQ/질문 임베딩
    - `gpt-4.1-mini` : 질문 리라이트(FAQ 스타일로 재해석)
  - **Pinecone** : 벡터 DB (namespace: `default`)
- **데이터 & 로그**
  - Q&A 데이터: 제공된 엑셀을 정제한 `qa_clean.csv`
  - DB: SQLite (+ SQLAlchemy ORM)
    - `ChatLog` 테이블에 `question`, `answer`, `source_question`, `score`, `created_at` 기록
- **배포**
  - **Render** Web Service에 FastAPI 앱 배포
  - `/health` 헬스 체크, `/chat` 질의응답 API 제공

### 2.2 프론트엔드

- **Next.js (App Router)** + **React**
  - `app/page.tsx` : 메인 챗봇 화면
  - `app/api/chat/route.ts` : Next API → FastAPI `/chat` 프록시
- **TypeScript** : 메시지/세션 타입 정의
- **Tailwind CSS** : Perso.ai 톤에 맞춘 라이트/심플한 UI
- **Vercel** : 프론트엔드 호스팅 및 CI/CD

---

## 3. 벡터 DB 및 임베딩 방식

### 3.1 인덱싱 흐름

1. `qa_clean.csv` 로딩  
   - 컬럼: `id`, `question`, `answer`, (`category` 옵션)
2. 각 행을 하나의 **Q&A 블록 텍스트**로 합침
   ```text
   Q: {question}
   A: {answer}
3. OpenAI text-embedding-3-small로 임베딩 생성

4. Pinecone 인덱스에 업서트

    - id : Q&A 식별자

    - values : 임베딩 벡터

    - metadata : { id, question, answer, (category) }

5. 32개 단위 배치 업서트 + 짧은 sleep으로 rate limit 보호
```
<설계 의도>
질문만 임베딩하는 것이 아니라, 질문+답변 전체 의미를 하나의 벡터에 담아 “표현이 조금 달라도 의미가 같은 질문”을 잘 찾도록 하기 위함입니다.
```

### 3.2 검색(온라인) 흐름

1. 사용자의 자연어 질문 수신

2. 질문 리라이트 (아래 4장 참조) 후, 최종 쿼리 텍스트 결정

3. text-embedding-3-small로 쿼리 임베딩 생성

4. Pinecone top_k=3 검색 (include_metadata=True)

5. 가장 높은 점수의 매칭 선택

6. score_threshold = 0.55 이상일 때만 매칭 성공으로 처리

---

## 4. 정확도 향상 전략
### 4.1 질문 리라이트 (LLM 기반 전처리)

- 모델: gpt-4.1-mini

- 역할: “FAQ 검색을 위한 질문 리라이터”

- 동작:
```
사용자의 자유로운 문장을 FAQ에 있을 법한 한 문장 질문으로 재작성

예시

“고객센터에 연결해줘”
→ “Perso.ai 고객센터는 어떻게 문의하나요?”

“요금 알려줘”
→ “Perso.ai 요금제는 어떻게 구성되어 있나요?”

강한 제약 조건:

새로운 사실/숫자/URL/이메일/전화번호 추가 금지

“질문 한 문장”만 생성 (답변 생성 금지)

temperature = 0 (변동 최소화)
```
이 단계에서 LLM은 검색 품질을 높이는 전처리 도구로만 사용되며,
최종 답변은 전적으로 FAQ 데이터에서만 가져옵니다.

### 4.2 Threshold 기반 필터링

- Pinecone에서 가장 높은 score를 가져오더라도,

    - score < 0.55 이면 **“매칭 실패”**로 간주

- 매칭 실패 시 응답:

    - "제공된 Q&A 데이터에서 적절한 답변을 찾지 못했습니다."

- 필요 시, 내부적으로는 source_question, score를 로그로 남겨 품질 분석에 활용

### 4.3 할루시네이션 차단

- LLM이 최종 답변을 생성하는 구조를 사용하지 않음

    - 사용자가 보는 답변은 항상 qa_clean.csv의 answer 필드 그대로

- LLM은 오직:

    - 질문 리라이트

    - 벡터 검색 품질 향상을 위한 보조 역할

- Threshold를 통해 애매한 경우 “모른다”라고 말하도록 설계

결과적으로,

“데이터셋에 있는 내용만 말한다”는 과제 요구사항을 충족하면서 사용자의 다양한 표현도 안정적으로 처리할 수 있도록 구성했습니다.

---

## 5. UI / UX 요약

- 좌측 패널

    - Perso.ai 로고 + “Perso.ai Support”

    - 최근 대화 리스트 (세션 단위)

    - “새 대화” 버튼

- 중앙 패널

    - 메인 채팅 영역

    - 사용자 말풍선: 우측, 파란색 그라디언트

    - 봇 말풍선: 좌측, 라이트 그레이/화이트

    - 새 메시지 수신 시 채팅 영역 자동 스크롤

- 우측 패널

    - 자주 묻는 질문(FAQ)을 빠르게 물어볼 수 있는 빠른 질문 버튼들

전체적으로 Perso.ai 공식 페이지의 밝은 분위기를 참고한 라이트톤 UI로 구성했습니다.

---

## 6. 배포 및 접근 방식

- 백엔드 (FastAPI)

    - Render Web Service로 배포

    - 주요 엔드포인트:

        - GET /health : 상태 체크

        - POST /chat : 챗봇 질의응답

        - GET /logs : 최근 Q&A 로그 조회(개발용)

- 프론트엔드 (Next.js)

    - Vercel에 배포

    - Next API Route /api/chat에서

        - NEXT_PUBLIC_API_BASE_URL 환경변수로 FastAPI URL을 참조하고,이를 /chat으로 프록시 요청