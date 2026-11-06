// 브라우저 -> 여기(Next.js 서버) -> FastAPI /api/chat
// API_BASE_URL은 서버에서만 읽으므로 브라우저에 노출되지 않는다.
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const base = process.env.API_BASE_URL;
  if (!base) {
    return NextResponse.json({ error: "API_BASE_URL이 설정되지 않았습니다." }, { status: 500 });
  }

  // 1) 입력 검사: 비어 있으면 FastAPI까지 보내지 않는다 (Gemini 비용 절약)
  let message = "";
  try {
    const body = await req.json();
    message = typeof body?.message === "string" ? body.message.trim() : "";
  } catch {
    return NextResponse.json({ error: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }
  if (!message) {
    return NextResponse.json({ error: "메시지를 입력해 주세요." }, { status: 400 });
  }

  // 2) FastAPI로 전달
  try {
    const res = await fetch(`${base}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json({ error: `서버 오류 (${res.status})` }, { status: 502 });
    }
    const data = await res.json();
    if (typeof data?.answer !== "string") {
      return NextResponse.json({ error: "응답 형식이 올바르지 않습니다." }, { status: 502 });
    }
    return NextResponse.json(data);
  } catch {
    // uvicorn이 꺼져 있을 때 등
    return NextResponse.json({ error: "API 서버에 연결하지 못했습니다." }, { status: 502 });
  }
}