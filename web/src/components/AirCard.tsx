import { getAirQuality } from "@/lib/api";
import { fmtIso, val } from "@/lib/format";
import { CardError, CardShell, Notes, Row } from "./Card";

const TITLE = "대기질";

export default async function AirCard({ location }: { location: string }) {
  const r = await getAirQuality(location);
  if (!r.ok) return <CardError title={TITLE} error={r.error} />;

  return (
    <CardShell
      title={TITLE}
      footer={
        <>
          측정소 {r.station_name} ({r.station_distance_km}km) · 측정 {r.data_time} · 수집{" "}
          {fmtIso(r.collected_at)}
        </>
      }
    >
      <Row label="미세먼지 (PM10)" value={`${val(r.pm10, " ㎍/㎥")} · ${r.pm10_grade}`} />
      <Row label="초미세먼지 (PM2.5)" value={`${val(r.pm25, " ㎍/㎥")} · ${r.pm25_grade}`} />
      <Notes notes={r.data_notes} />
    </CardShell>
  );
}