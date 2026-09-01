// 007バイクツーリングPWAの利用実績(stats.json)を取得するヘルパー。
// Astroのフロントマターはリクエストごとに再実行されるため、SSR応答ごとに
// 取得する。利用実績は運用データなので、ウォームしたLambdaのモジュール
// スコープへ保持して古い値を表示しない。
const STATS_URL = 'https://touring.zer0-infra.com/stats.json';

export type TouringStats = {
  history: { date: string; count: number }[];
  total: number;
  updatedAt: string;
};

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
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(STATS_URL, {
      signal: controller.signal,
      cache: 'no-store',
    });
    clearTimeout(timeout);
    if (res.ok) {
      const json = await res.json();
      if (isValidStats(json)) return json;
    }
  } catch {
    // 統計取得失敗は通常ページのSSRを失敗させず、グラフだけを非表示にする。
  }
  return null;
}
