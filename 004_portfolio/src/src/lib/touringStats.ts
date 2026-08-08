// 007バイクツーリングPWAの利用実績(stats.json)を取得するヘルパー。
// Astroのフロントマターはリクエストごとに再実行されるため、ここでモジュール
// スコープにキャッシュを持たせる(Lambda実行環境がウォームな間は保持され、
// 004のSSRからCloudFront経由で毎リクエスト外部fetchするのを避ける)。
const STATS_URL = 'https://touring.zer0-infra.com/stats.json';
const CACHE_TTL_MS = 5 * 60 * 1000;

export type TouringStats = {
  history: { date: string; count: number }[];
  total: number;
  updatedAt: string;
};

let cache: { data: TouringStats | null; expiresAt: number } | null = null;

function isValidStats(data: unknown): data is TouringStats {
  if (!data || typeof data !== 'object') return false;
  const d = data as Record<string, unknown>;
  if (typeof d.total !== 'number' || typeof d.updatedAt !== 'string') return false;
  if (!Array.isArray(d.history)) return false;
  return d.history.every(
    (h) => h && typeof h === 'object' && typeof (h as any).date === 'string' && typeof (h as any).count === 'number'
  );
}

export async function getTouringStats(): Promise<TouringStats | null> {
  if (cache && cache.expiresAt > Date.now()) return cache.data;

  let data: TouringStats | null = null;
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(STATS_URL, { signal: controller.signal });
    clearTimeout(timeout);
    if (res.ok) {
      const json = await res.json();
      if (isValidStats(json)) data = json;
    }
  } catch {
    data = null;
  }

  cache = { data, expiresAt: Date.now() + CACHE_TTL_MS };
  return data;
}
