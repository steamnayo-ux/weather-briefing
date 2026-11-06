"use client";

import { useState } from "react";
import type { ChatReply } from "@/lib/api";

// 화면에 쌓는 대화 한 줄
type Turn =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; tools: string[] }
  | { role: "error"; text: string };

export default function ChatPanel() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send() {
    const message = input.trim();
    if (!message || loading) return; // 빈 입력, 중복 전송 방지
    setTurns((t) => [...t, { role: "user", text: message }]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      if (!res.ok) {
        setTurns((t) => [...t, { role: "error", text: data?.error ?? "오류가 발생했습니다." }]);
      } else {
        const reply = data as ChatReply;
        // 사용한 도구 이름만 중복 없이 표시
        const tools = [...new Set(reply.tool_calls.map((c) => c.name))];
        setTurns((t) => [...t, { role: "assistant", text: reply.answer, tools }]);
      }
    } catch {
      setTurns((t) => [...t, { role: "error", text: "네트워크 오류가 발생했습니다." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="mb-3 text-lg font-semibold">날씨 비서에게 물어보기</h2>

      <div className="mb-3 flex max-h-96 flex-col gap-2 overflow-y-auto">
        {turns.length === 0 && (
          <p className="text-sm text-zinc-500">예: "분당구 오늘 러닝해도 돼?"</p>
        )}
        {turns.map((t, i) => (
          <div
            key={i}
            className={
              t.role === "user"
                ? "self-end rounded-lg bg-zinc-100 px-3 py-2 text-sm dark:bg-zinc-800"
                : t.role === "error"
                ? "rounded-lg border border-red-300 px-3 py-2 text-sm text-red-600"
                : "rounded-lg border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-700"
            }
          >
            <p className="whitespace-pre-wrap">{t.text}</p>
            {t.role === "assistant" && t.tools.length > 0 && (
              <p className="mt-1 text-xs text-zinc-500">사용한 도구: {t.tools.join(", ")}</p>
            )}
          </div>
        ))}
        {loading && <p className="text-sm text-zinc-500">답변을 만드는 중…</p>}
      </div>

      {/* form 태그로 Enter 전송을 자연스럽게 처리 */}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="질문을 입력하세요"
          className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-transparent"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          전송
        </button>
      </form>
    </section>
  );
}