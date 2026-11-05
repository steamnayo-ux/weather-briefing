import { getHourly } from "@/lib/api";
import { fmtCompact, fmtIso, val } from "@/lib/format";
import { CardError, CardShell } from "./Card";

const TITLE = "시간대별 예보";
const SHOW = 8; // 앞쪽 8시간만 표시

export default async function HourlyCard({ location }: { location: string }) {
  const r = await getHourly(location);
  if (!r.ok) return <CardError title={TITLE} error={r.error} />;

  const rows = r.hours.slice(0, SHOW);
  const s = r.summary;

  return (
    <CardShell
      title={TITLE}
      footer={<>예보 기준 {fmtCompact(r.forecast_base)} · 수집 {fmtIso(r.collected_at)}</>}
    >
      <p className="text-sm text-zinc-500">
        {r.date} 남은 시간 기준 최저/최고 {val(s.temp_min_c, "°")} / {val(s.temp_max_c, "°")} · 최대 강수확률{" "}
        {val(s.precipitation_probability_max, "%")}
      </p>
      {/* 좁은 화면에서는 표 안에서만 가로 스크롤 */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm">
          <thead className="text-left text-xs text-zinc-500">
            <tr>
              <th className="py-1">시각</th>
              <th>기온</th>
              <th>하늘</th>
              <th>강수확률</th>
              <th>바람</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.time} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-1.5">{h.time}</td>
                <td>{val(h.temperature_c, "°")}</td>
                <td>{h.sky}</td>
                <td>{val(h.precipitation_probability, "%")}</td>
                <td>{val(h.wind_speed_ms, " m/s")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CardShell>
  );
}