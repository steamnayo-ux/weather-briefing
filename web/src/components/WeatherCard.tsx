import { getWeather } from "@/lib/api";
import { fmtCompact, fmtIso, val } from "@/lib/format";
import { CardError, CardShell, Notes, Row } from "./Card";

const TITLE = "현재 날씨";

export default async function WeatherCard({ location }: { location: string }) {
  const r = await getWeather(location);
  if (!r.ok) return <CardError title={TITLE} error={r.error} />;

  return (
    <CardShell
      title={TITLE}
      footer={
        <>
          관측 {fmtCompact(r.observed_at)} · 예보 기준 {fmtCompact(r.forecast_base)} ·
          수집 {fmtIso(r.collected_at)}
        </>
      }
    >
      <p className="text-4xl font-bold">
        {val(r.temperature_c, "°C")}{" "}
        <span className="text-base font-normal text-zinc-500">{r.sky}</span>
      </p>
      <Row label="습도" value={val(r.humidity_pct, "%")} />
      <Row label="강수" value={`${r.precipitation_type} (${val(r.precipitation_mm, "mm")})`} />
      <Row label="바람" value={val(r.wind_speed_ms, " m/s")} />
      {/* 현재(관측)와 오늘 예보 최저/최고는 출처가 달라 값이 어긋날 수 있어서 라벨을 나눈다 */}
      <Row
        label="오늘 예보 최저/최고"
        value={`${val(r.temp_min_c, "°")} / ${val(r.temp_max_c, "°")}`}
      />
      <Row label="오늘 최대 강수확률" value={val(r.precipitation_probability_max, "%")} />
      {/* LLM이 아니라 코드가 고정하는 문구: warnings가 비어도 "특보 없음"이라고 하지 않는다 */}
      <Row label="기상특보" value={r.special_weather_report === "not_provided" ? "미제공" : r.special_weather_report} />
      <Notes notes={r.data_notes} />
    </CardShell>
  );
}