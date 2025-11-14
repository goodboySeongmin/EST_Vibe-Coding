"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type ChatMessage = {
  id: string;
  role: "user" | "bot";
  content: string;
  createdAt: string;
  sourceQuestion?: string;
  score?: number;
};

type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
  messages: ChatMessage[];
};

const STORAGE_KEY = "vibecoding_chat_sessions_v3";

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

const QUICK_PROMPTS = [
  "Perso.ai는 어떤 서비스야?",
  "요금제가 어떻게 구성되어 있어?",
  "고객센터에 문의하려면 어떻게 해야 해?",
  "지원되는 언어가 뭐가 있어?",
];

export default function HomePage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // 세션 로딩
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as ChatSession[];
      if (Array.isArray(parsed) && parsed.length > 0) {
        setSessions(parsed);
        setActiveId(parsed[0].id);
      }
    } catch (e) {
      console.error("Failed to load sessions", e);
    }
  }, []);

  // 세션 저장
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    } catch (e) {
      console.error("Failed to save sessions", e);
    }
  }, [sessions]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? null,
    [sessions, activeId]
  );

  const startNewSession = () => {
    const id = createId();
    const now = new Date().toISOString();
    const newSession: ChatSession = {
      id,
      title: "새 대화",
      createdAt: now,
      messages: [],
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveId(id);
  };

  const upsertMessage = (sessionId: string, msg: ChatMessage) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === sessionId
          ? {
              ...s,
              title:
                s.messages.length === 0 && msg.role === "user"
                  ? msg.content.slice(0, 30)
                  : s.title,
              messages: [...s.messages, msg],
            }
          : s
      )
    );
  };

  const sendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    // 세션 없으면 새로 생성
    let sessionId = activeId;
    if (!sessionId) {
      const id = createId();
      const now = new Date().toISOString();
      const newSession: ChatSession = {
        id,
        title: trimmed.slice(0, 30),
        createdAt: now,
        messages: [],
      };
      setSessions((prev) => [newSession, ...prev]);
      setActiveId(id);
      sessionId = id;
    }

    const now = new Date().toISOString();
    const userMsg: ChatMessage = {
      id: createId(),
      role: "user",
      content: trimmed,
      createdAt: now,
    };
    upsertMessage(sessionId!, userMsg);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      });

      let data: any;
      try {
        data = await res.json();
      } catch (err) {
        const raw = await res.text();
        console.error("Raw response", res.status, raw);
        data = { error: "JSON 파싱 실패" };
      }

      let botContent = "";
      if (data?.error) {
        botContent = `⚠️ ${data.error}`;
      } else if (!data?.found) {
        botContent =
          "제공된 Q&A 데이터에서 적절한 답변을 찾지 못했습니다.\n" +
          (data?.sourceQuestion
            ? `(가장 가까운 질문: ${data.sourceQuestion}${
                typeof data.score === "number"
                  ? `, 유사도: ${data.score.toFixed(3)}`
                  : ""
              })`
            : "");
      } else {
        botContent = data.answer ?? "";
      }

      const botMsg: ChatMessage = {
        id: createId(),
        role: "bot",
        content: botContent,
        createdAt: new Date().toISOString(),
        sourceQuestion: data?.sourceQuestion,
        score: typeof data?.score === "number" ? data.score : undefined,
      };

      upsertMessage(sessionId!, botMsg);
    } catch (err) {
      console.error(err);
      const botMsg: ChatMessage = {
        id: createId(),
        role: "bot",
        content: "서버와 통신 중 오류가 발생했습니다.",
        createdAt: new Date().toISOString(),
      };
      upsertMessage(sessionId!, botMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await sendMessage(input);
  };

  const handleQuickPrompt = (prompt: string) => {
    void sendMessage(prompt);
  };

  return (
    <main className="h-screen bg-gradient-to-b from-sky-50 via-white to-slate-50 text-slate-900 text-[16px] md:text-[17px] overflow-hidden">
      {/* 화면 전체 높이를 쓰고 내부만 스크롤 */}
      <div className="h-full max-w-[1500px] mx-auto px-6 py-8 flex gap-5">
        {/* 좌측: 최근 대화 리스트 */}
        <nav className="hidden md:flex flex-col w-60 rounded-2xl bg-white/90 border border-slate-200 shadow-md">
          <div className="px-4 pt-4 pb-2 flex items-center justify-between border-b border-slate-100">
            <span className="text-sm font-medium text-slate-600">
              최근 대화
            </span>
            <button
              onClick={startNewSession}
              className="text-xs font-semibold px-3 py-1.5 rounded-full bg-sky-500 text-white hover:bg-sky-600 shadow-sm transition"
            >
              새 대화
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-2 pb-4">
            {sessions.length === 0 && (
              <p className="text-sm text-slate-400 px-2 mt-3">
                아직 대화가 없습니다.
              </p>
            )}
            <div className="space-y-1 mt-2">
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setActiveId(s.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-xl text-sm transition ${
                    s.id === activeId
                      ? "bg-sky-50 text-slate-900 border border-sky-200"
                      : "hover:bg-slate-50 text-slate-600"
                  }`}
                >
                  <div className="truncate font-medium">{s.title}</div>
                  <div className="text-[11px] text-slate-400">
                    {new Date(s.createdAt).toLocaleString()}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </nav>

        {/* 중앙 + 우측 */}
        <section className="flex-1 flex flex-col gap-4 min-h-0">
          {/* 상단 글로벌 헤더 */}
          <header className="rounded-2xl bg-white/90 border border-slate-200 px-5 py-4 flex items-center justify-between shadow-md">
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-3xl overflow-hidden bg-white flex items-center justify-center">
                <img
                  src="/perso-logo.png"
                  alt="Perso.ai 로고"
                  className="h-full w-full object-contain p-1"
                />
              </div>
              <div className="flex flex-col">
                <span className="text-2xl font-semibold">Perso.ai Support</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
              <span className="text-sm text-slate-500">서비스 정상</span>
            </div>
          </header>

          {/* 가운데/오른쪽 영역 */}
          <div className="flex gap-2 flex-1 min-h-0">
            {/* 채팅 영역 */}
            <div className="flex-1 flex flex-col rounded-2xl bg-white/95 border border-slate-200 shadow-md min-h-0">
              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                {!activeSession || activeSession.messages.length === 0 ? (
                  <div className="mt-4 text-[15px] md:text-[16px] text-slate-600">
                    <p className="mb-2">
                      안녕하세요, Perso.ai FAQ 챗봇입니다!
                    </p>
                    <p className="mb-1">
                      서비스 소개, 요금제, 지원 언어, 고객센터 문의 방법 등
                      Perso.ai와 관련된 질문을 입력해 보세요.
                    </p>
                    <p className="text-xs text-slate-400">
                      예) &ldquo;Perso.ai는 어떤 서비스야?&rdquo;,{" "}
                      &ldquo;요금제 알려줘&rdquo;, &ldquo;고객센터에
                      연결해줘&rdquo;
                    </p>
                  </div>
                ) : (
                  activeSession.messages.map((m) => (
                    <div
                      key={m.id}
                      className={`flex ${
                        m.role === "user" ? "justify-end" : "justify-start"
                      }`}
                    >
                      <div className="max-w-[85%] md:max-w-[78%]">
                        <div
                          className={`rounded-3xl px-4 py-3 whitespace-pre-line text-[16px] md:text-[17px] leading-relaxed shadow-sm transition-all ${
                            m.role === "user"
                              ? "bg-gradient-to-r from-sky-500 to-sky-400 text-white"
                              : "bg-slate-50 text-slate-900 border border-slate-200"
                          }`}
                        >
                          {m.content}
                        </div>
                      </div>
                    </div>
                  ))
                )}

                {loading && (
                  <div className="text-xs text-slate-400 mt-2">
                    답변을 입력하는 중입니다...
                  </div>
                )}
              </div>

              {/* 입력창 */}
              <form
                onSubmit={handleSubmit}
                className="border-t border-slate-200 px-5 py-3 flex gap-2 items-center rounded-b-2xl bg-slate-50/60"
              >
                <input
                  className="flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-[16px] md:text-[17px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500/80"
                  placeholder="질문을 입력하세요..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  className="rounded-xl px-4 py-2.5 text-sm font-semibold text-white bg-sky-500 hover:bg-sky-600 disabled:opacity-50 transition"
                >
                  보내기
                </button>
              </form>
            </div>

            {/* 오른쪽: 빠른 질문 */}
            <aside className="hidden lg:flex flex-col w-72 rounded-2xl bg-white/90 border border-slate-200 p-4 shadow-md">
              <div className="mb-2">
                <h2 className="text-sm font-semibold text-slate-700 mb-1">
                  빠른 질문
                </h2>
                <p className="text-xs text-slate-500 mb-2">
                  자주 묻는 질문을 바로 클릭해서 물어볼 수 있어요.
                </p>
                <div className="flex flex-col gap-2">
                  {QUICK_PROMPTS.map((q) => (
                    <button
                      key={q}
                      onClick={() => handleQuickPrompt(q)}
                      disabled={loading}
                      className="w-full text-left justify-start whitespace-nowrap text-xs px-4 py-2 rounded-full border border-slate-200 bg-slate-50 hover:bg-sky-50 hover:border-sky-200 text-slate-700 disabled:opacity-50 transition"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </aside>
          </div>
        </section>
      </div>
    </main>
  );
}
