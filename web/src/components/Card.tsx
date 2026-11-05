import type { ReactNode } from "react";
import type { ApiError } from "@/lib/api";

// 카드 공통 틀: 제목, 본문, 하단 기준 시각
export function CardShell({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="mb-3 text-sm font-semibold text-zinc-500">{title}</h2>
      <div className="space-y-3">{children}</div>
      {footer && (
        <div className="mt-4 border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800">
          {footer}
        </div>
      )}
    </section>
  );
}

// 실패해도 이 카드만 오류를 보여 주고 나머지 카드는 그대로 뜬다.
export function CardError({ title, error }: { title: string; error: ApiError }) {
  return (
    <CardShell title={title}>
      <p className="text-sm text-red-600 dark:text-red-400">{error.message}</p>
      <p className="text-xs text-zinc-500">오류 코드: {error.code}</p>
    </CardShell>
  );
}

export function CardSkeleton({ title }: { title: string }) {
  return (
    <CardShell title={title}>
      <div className="h-24 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
    </CardShell>
  );
}

// label : value 한 줄
export function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="text-zinc-500">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

// data_notes 표시 (비어 있으면 아무것도 그리지 않는다)
export function Notes({ notes }: { notes: unknown[] }) {
  if (!notes?.length) return null;
  return (
    <ul className="list-disc space-y-1 pl-5 text-xs text-amber-700 dark:text-amber-400">
      {notes.map((n, i) => (
        <li key={i}>{typeof n === "string" ? n : JSON.stringify(n)}</li>
      ))}
    </ul>
  );
}