// "20261105 1400" -> "11/5 14:00"
export function fmtCompact(s: string | null | undefined): string {
  const m = s?.match(/^\d{4}(\d{2})(\d{2}) (\d{2})(\d{2})$/);
  return m ? `${Number(m[1])}/${Number(m[2])} ${m[3]}:${m[4]}` : (s ?? "-");
}

// "2026110515" -> "11/5 15시"
export function fmtAnnounced(s: string | null | undefined): string {
  const m = s?.match(/^\d{4}(\d{2})(\d{2})(\d{2})$/);
  return m ? `${Number(m[1])}/${Number(m[2])} ${m[3]}시` : (s ?? "-");
}

// "2026-11-05T15:13:05+09:00" -> "11/5 15:13" (시간대 변환 없이 문자열 그대로 읽는다)
export function fmtIso(s: string | null | undefined): string {
  const m = s?.match(/^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  return m ? `${Number(m[1])}/${Number(m[2])} ${m[3]}:${m[4]}` : (s ?? "-");
}

// 값이 없으면 "-"로 보여 준다. (0은 정상 값이라 그대로 표시)
export function val(v: number | string | null | undefined, unit = ""): string {
  return v === null || v === undefined || v === "" ? "-" : `${v}${unit}`;
}