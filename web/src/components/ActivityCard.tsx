import { getRecommendation } from "@/lib/api";
import { fmtCompact, fmtIso, val } from "@/lib/format";
import { CardError, CardShell, Notes, Row } from "./Card";

const TITLE = "활동 추천";

// 색만으로 구분하지 않고 글자도 같이 보여 준다. 모르는 판정은 회색.
function badgeClass(verdict: string): string {
  if (verdict === "좋음") return "bg-green-100 text-green-800";
  if (verdict === "주의") return "bg-amber-100 text-amber-800";
  if (["나쁨", "위험", "비추천"].includes(verdict)) return "bg-red-100 text-red-800";
  return "bg-zinc-100 text-zinc-700";
}

export default async function ActivityCard({
  location,
  activity,
}: {
  location: string;
  activity: string;
}) {
  const r = await getRecommendation(location, activity);
  if (!r.ok) return <CardError title={`${TITLE} (${activity})`} error={r.error} />;

  const d = r.details;
  const extra = [...(r.items ?? []), ...(r.notes ?? [])];

  return (
    <CardShell
      title={`${TITLE} (${r.activity})`}
      footer={
        <>
          예보 기준 {fmtCompact(r.forecast_base)} · 수집 {fmtIso(r.collected_at)} · 기상특보{" "}
          {r.special_weather_report === "not_provided" ? "미제공" : r.special_weather_report}
        </>
      }
    >
      <p>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${badgeClass(r.verdict)}`}>
          {r.verdict}
        </span>
        <span className="ml-2 text-xs text-zinc-500">판단 구간 {r.checked_hours}</span>
      </p>

      {/* 판정 근거는 코드가 만든 reasons를 그대로 보여 준다 */}
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {r.reasons.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>

      {r.best_window && (
        <Row
          label="가장 좋은 시간"
          value={`${r.best_window.start}~${r.best_window.end} (${r.best_window.hours}시간)`}
        />
      )}
      <Row label="체감 최저" value={val(d.feels_like_min_c, "°")} />
      <Row label="최대 강수확률" value={val(d.precipitation_probability_max, "%")} />
      <Row label="평균 습도" value={val(d.humidity_avg_pct, "%")} />
      <Row label="최대 바람" value={val(d.wind_max_ms, " m/s")} />
      <Row label="미세먼지" value={val(d.dust_grade)} />
      <Row label="자외선 지수" value={val(d.uv_index)} />

      <Notes notes={extra} />
      <Notes notes={r.data_notes} />
    </CardShell>
  );
}