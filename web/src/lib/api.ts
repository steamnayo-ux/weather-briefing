// 서버 컴포넌트에서만 호출한다. 브라우저가 8000번을 직접 부르지 않으므로 CORS가 필요 없다.
const BASE = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

// ⚠️ 파라미터 이름이 api_read.py와 다르면 이 두 줄만 고친다.
const LOCATION_PARAM = "location";
const ACTIVITY_PARAM = "activity";

export type ApiError = { code: string; message: string; candidates?: unknown[] };
export type Failure = { ok: false; error: ApiError };

// ---------- 응답 타입 (실제 응답 JSON 기준) ----------
export type WeatherData = {
  ok: true;
  location: string;
  collected_at: string;
  observed_at: string;
  forecast_base: string;
  forecast_for: string;
  temperature_c: number | null;
  humidity_pct: number | null;
  precipitation_mm: number | null;
  precipitation_type: string;
  wind_speed_ms: number | null;
  sky: string;
  precipitation_probability: number | null;
  temp_min_c: number | null;
  temp_max_c: number | null;
  precipitation_probability_max: number | null;
  data_notes: string[];
  special_weather_report: string; // "not_provided"
};

export type HourlyItem = {
  time: string;
  temperature_c: number | null;
  sky: string;
  precipitation_type: string;
  precipitation_probability: number | null;
  precipitation_amount: string;
  snow_amount: string;
  humidity_pct: number | null;
  wind_speed_ms: number | null;
  wind_chill_c: number | null;
};

export type HourlyData = {
  ok: true;
  location: string;
  collected_at: string;
  forecast_base: string;
  date: string;
  summary: {
    temp_min_c: number | null;
    temp_max_c: number | null;
    precipitation_probability_max: number | null;
    precipitation_times: string[];
  };
  hours: HourlyItem[];
};

export type AirData = {
  ok: true;
  location: string;
  station_name: string;
  station_distance_km: number;
  data_time: string;
  pm10: number | null;
  pm10_grade: string;
  pm25: number | null;
  pm25_grade: string;
  collected_at: string;
  data_notes: string[];
};

export type UvData = {
  ok: true;
  region: string;
  area_level: string;
  announced_at: string;
  date: string;
  uv_max: number | null;
  uv_level: string;
  uv_max_at: string;
  window: string;
  points: { time: string; uv: number | null; level: string }[];
};

export type RecommendData = {
  ok: true;
  location: string;
  date: string;
  collected_at: string;
  forecast_base: string;
  activity: string;
  verdict: string;
  reasons: string[];
  items: unknown[]; // 모양을 아직 못 봐서 느슨하게 둔다
  notes: unknown[];
  checked_hours: string;
  details: {
    temp_min_c: number | null;
    temp_max_c: number | null;
    feels_like_min_c: number | null;
    precipitation_probability_max: number | null;
    precipitation_times: string[];
    humidity_avg_pct: number | null;
    wind_max_ms: number | null;
    dust_grade: string | null;
    uv_index: number | null;
  };
  best_window?: { start: string; end: string; hours: number } | null;
  data_notes: string[];
  special_weather_report: string;
};

// ---------- 공통 호출 ----------
function fail(code: string, message: string): Failure {
  return { ok: false, error: { code, message } };
}

async function getJson<T extends { ok: true }>(
  path: string,
  params: Record<string, string>,
): Promise<T | Failure> {
  const url = new URL(path, BASE);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);

  try {
    // 날씨는 매번 새로 받아야 하므로 캐시하지 않는다.
    const res = await fetch(url, { cache: "no-store" });
    const body = await res.json();
    if (body && typeof body === "object" && "ok" in body) {
      return body as T | Failure; // 성공(ok:true)과 서비스 오류(ok:false) 모두 이 모양
    }
    return fail("bad_response", "예상하지 못한 응답 형식이에요.");
  } catch {
    // 서버가 꺼져 있거나 JSON이 아닌 응답
    return fail("network", "API 서버에서 응답을 받지 못했어요. uvicorn이 켜져 있는지 확인해 주세요.");
  }
}

export const getWeather = (loc: string) =>
  getJson<WeatherData>("/api/weather", { [LOCATION_PARAM]: loc });
export const getHourly = (loc: string) =>
  getJson<HourlyData>("/api/hourly", { [LOCATION_PARAM]: loc });
export const getAirQuality = (loc: string) =>
  getJson<AirData>("/api/air-quality", { [LOCATION_PARAM]: loc });
export const getUv = (loc: string) =>
  getJson<UvData>("/api/uv", { [LOCATION_PARAM]: loc });
export const getRecommendation = (loc: string, activity: string) =>
  getJson<RecommendData>("/api/recommendations", {
    [LOCATION_PARAM]: loc,
    [ACTIVITY_PARAM]: activity,
  });