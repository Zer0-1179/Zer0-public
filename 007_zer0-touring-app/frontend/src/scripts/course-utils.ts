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
