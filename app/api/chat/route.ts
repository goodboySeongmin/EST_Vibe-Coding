// app/api/chat/route.ts
import { NextResponse } from "next/server";
import OpenAI from "openai";
import { Pinecone } from "@pinecone-database/pinecone";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY!,
});

const pc = new Pinecone({
  apiKey: process.env.PINECONE_API_KEY!,
});

// 우리가 만든 인덱스 + namespace
const indexName = process.env.PINECONE_INDEX_NAME!;
const index = pc.index(indexName).namespace("default"); // Python에서 default namespace 사용

type ChatRequestBody = {
  message?: string;
};

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as ChatRequestBody;

    if (!body.message || body.message.trim().length === 0) {
      return NextResponse.json(
        { error: "message 필드가 비어 있습니다." },
        { status: 400 }
      );
    }

    const userMessage = body.message.trim();

    // 3-1) 질문 리라이트 (FAQ 스타일로 재해석)
    const rewritten = await rewriteQuery(openai, userMessage);
    const queryText = rewritten || userMessage;

    // 3-2) 임베딩 생성은 리라이트된 문장으로
    const embRes = await openai.embeddings.create({
    model: "text-embedding-3-small",
    input: queryText,
    });

    const vector = embRes.data[0].embedding;

    // 2) Pinecone 검색
    const queryRes = await index.query({
      topK: 3,
      vector,
      includeMetadata: true,
    });

    const matches = queryRes.matches ?? [];
    if (matches.length === 0) {
      return NextResponse.json({
        found: false,
        answer: "제공된 Q&A 데이터에서 적절한 답변을 찾지 못했습니다.",
        sourceQuestion: null,
        score: null,
      });
    }

    // 3) 최고 점수 매칭 선택 + threshold 적용
    const best = matches.sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0];
    const score = best.score ?? 0;

    const threshold = 0.6; // Python에서 쓰던 값과 동일
    const question = (best.metadata as any)?.question as string | undefined;
    const answer = (best.metadata as any)?.answer as string | undefined;

    if (!answer || score < threshold) {
      return NextResponse.json({
        found: false,
        answer: "제공된 Q&A 데이터에서 적절한 답변을 찾지 못했습니다.",
        sourceQuestion: question ?? null,
        score,
      });
    }

    return NextResponse.json({
      found: true,
      answer,
      sourceQuestion: question ?? null,
      score,
    });
  } catch (err) {
    console.error("Error in POST /api/chat:", err);
    return NextResponse.json(
      { error: "서버 내부 오류가 발생했습니다." },
      { status: 500 }
    );
  }
}
// route.ts 상단 import 밑에 붙여두면 됨

async function rewriteQuery(openai: OpenAI, userMessage: string): Promise<string> {
  // 너무 짧거나 애매하면 그냥 원본 그대로 쓰게 할 수도 있음
  if (userMessage.length < 2) return userMessage;

  const systemPrompt = `
너는 FAQ 검색을 위한 "질문 리라이터"야.

- 사용자가 한 말을, Perso.ai FAQ에 있을 법한 "완전한 한 문장 질문"으로 바꿔.
- 새 사실, 숫자, 이메일, URL, 전화번호, 기능 등을 절대 추가하지 마.
- 서비스 이름(Perso.ai)처럼 문맥상 당연한 것만 보완해도 돼.
- 예시:
  - "고객센터에 연결해줘" -> "Perso.ai 고객센터는 어떻게 문의하나요?"
  - "요금 알려줘" -> "Perso.ai 요금제는 어떻게 구성되어 있나요?"
- 답변을 만들지 말고, 오직 "질문 한 문장"만 내보내.
`;

  const res = await openai.chat.completions.create({
    model: "gpt-4.1-mini", // 또는 사용 가능한 경량 모델
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userMessage },
    ],
    temperature: 0.0, // 창의성 최소화
  });

  const text = res.choices[0]?.message?.content?.trim() ?? "";
  // 혹시 이상한 응답이면 그냥 원본 질문 사용
  if (!text || text.length < 3) return userMessage;

  return text;
}
