export interface WeatherMeta {
  icon: string;
  score: number;
  label: string;
}

export function escHtml(s: unknown): string {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function fmtHours(h: number): string {
  const rounded = Math.ceil(Math.round(h * 60) / 10) * 10;  // 10分単位で切り上げ
  const hrs = Math.floor(rounded / 60);
  const mins = rounded % 60;
  if (hrs === 0) return `約${mins}分`;
  if (mins === 0) return `約${hrs}時間`;
  return `約${hrs}時間${mins}分`;
}

export function getWeatherMeta(code: number): WeatherMeta {
  if (code === 0)                 return { icon: '☀️', score: 5, label: '絶好の日和！' };
  if (code <= 2)                  return { icon: '🌤', score: 4, label: 'ツーリング向き' };
  if (code === 3)                 return { icon: '☁️', score: 3, label: 'まずまず' };
  if (code === 45 || code === 48) return { icon: '🌫', score: 2, label: '視界に注意' };
  if (code >= 51 && code <= 67)   return { icon: '🌧', score: 1, label: '雨天注意' };
  if (code >= 71 && code <= 77)   return { icon: '🌨', score: 1, label: '降雪注意' };
  if (code >= 80 && code <= 82)   return { icon: '🌦', score: 2, label: 'にわか雨注意' };
  if (code >= 95)                 return { icon: '⛈', score: 0, label: '走行危険' };
  return { icon: '🌤', score: 3, label: 'まずまず' };
}

interface SpotLike {
  name: string;
  lat?: number;
  lon?: number;
}

interface CourseLike {
  destination: string;
  dest_lat?: number;
  dest_lon?: number;
  outbound_spots?: SpotLike[];
  rest_spots?: SpotLike[];
}

/** Googleマップナビ起動用URLを組み立てる。origin判定はnullチェックで行う
 * （真偽値判定だと座標が0付近の場合に誤って起点なし扱いになるため）。 */
export function buildMapUrl(c: CourseLike, userLat: number | null, userLon: number | null): string {
  const dest = c.dest_lat != null && c.dest_lon != null
    ? `${c.dest_lat},${c.dest_lon}`
    : encodeURIComponent(c.destination);
  const spots = (c.outbound_spots ?? c.rest_spots ?? []).map((s) =>
    s.lat != null && s.lon != null ? `${s.lat},${s.lon}` : encodeURIComponent(s.name)
  );
  const hasOrigin = userLat != null && userLon != null;
  const coord = hasOrigin ? `${userLat.toFixed(6)},${userLon.toFixed(6)}` : '';
  const op = hasOrigin ? `&origin=${coord}` : '';
  const wp = spots.length ? `&waypoints=${spots.join('%7C')}` : '';
  return `https://www.google.com/maps/dir/?api=1${op}&destination=${dest}${wp}&travelmode=driving`;
}

export interface EnrichState {
  enriched: boolean;
  enrichFailed: boolean;
}

/** POST /api/enrich のレスポンス（または例外時はnull）から、コースの
 * _enriched/_enrichFailed 状態を決める。
 * 目的地ジオコーディングが失敗すると dest_lat が付かず天気も取れないままになるバグが
 * あったため、enriched=trueは「ジオコーディングまで成功した」ときのみとし、次回詳細画面を
 * 開いた時に再試行できるようにする。enrichFailedは「今開いている画面」に取得中...のまま
 * 止まらず終端状態（取得できませんでした）を表示するためのフラグ。 */
export function computeEnrichState(course: { dest_lat?: number; dest_weather_code?: number } | null): EnrichState {
  if (!course) return { enriched: false, enrichFailed: true };
  return {
    enriched: course.dest_lat !== undefined,
    enrichFailed: course.dest_weather_code === undefined,
  };
}
