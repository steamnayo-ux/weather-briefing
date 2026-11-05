import { getUv } from "@/lib/api";
import { fmtAnnounced, val } from "@/lib/format";
import { CardError, CardShell, Row } from "./Card";

const TITLE = "자외선";

export default async function UvCard({ location }: { location: string }) {
  const r = await getUv(location);
  if (!r.ok) return <CardError title={TITLE} error={r.error} />;

  return (
    <CardShell
      title={TITLE}
      footer={
        <>
          발표 {fmtAnnounced(r.announced_at)} · 지역 단위 {r.area_level} · 대상 시간 {r.window}
        </>
      }
    >
      <p className="text-4xl font-bold">
        {val(r.uv_max)}{" "}
        <span className="text-base font-normal text-zinc-500">{r.uv_level}</span>
      </p>
      <Row label="최대 시각" value={r.uv_max_at} />
      {r.points.map((p) => (
        <Row key={p.time} label={p.time} value={`${val(p.uv)} · ${p.level}`} />
      ))}
    </CardShell>
  );
}