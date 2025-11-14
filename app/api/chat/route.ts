// app/api/chat/route.ts
import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function POST(req: NextRequest) {
  try {
    const { message } = await req.json();

    if (!message || message.trim().length === 0) {
      return NextResponse.json(
        { error: "message 필드가 비어 있습니다." },
        { status: 400 }
      );
    }

    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error("API /api/chat error:", err);
    return NextResponse.json(
      { error: "서버와 통신 중 오류가 발생했습니다." },
      { status: 500 }
    );
  }
}
