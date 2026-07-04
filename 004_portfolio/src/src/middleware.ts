import { defineMiddleware } from 'astro:middleware';
import crypto from 'node:crypto';
import { SSMClient, GetParameterCommand } from '@aws-sdk/client-ssm';

// 全てのインラインスクリプトは nonce={Astro.locals.cspNonce} を付与済み
// （Nav.astro / BaseLayout.astro / templates/index.astro(ja,en) / templates/[category]/index.astro(ja,en)）。
// 2026-07-03以前はハッシュ全件を手動計算してハードコードする方式だったが、
// スクリプト変更のたびに複数箇所のハッシュ再計算が必要で壊れやすかったため、
// nonceベースに統一した（ハッシュはlambda.mjsのSTATIC_CSP側にのみ残す。
// そちらはインラインスクリプトを持たないAPIルート用のフォールバックのため実質未使用）。

// ── 006 CryptoBot 非公開統計ページの Basic 認証（2026-07-04）───────
// SSM SecureString "user:pass" を GetParameter で取得し比較する。
// モジュールスコープでTTLキャッシュしてコールドスタート以外は毎回SSMを叩かない。
const PRIVATE_PATH_PREFIX = '/ja/cryptobot-stats';
const AUTH_PARAM_NAME = '/Zer0/Portfolio/cryptobot-stats-auth';
const AUTH_CACHE_TTL_MS = 5 * 60 * 1000;

const ssm = new SSMClient({ region: process.env.AWS_REGION || 'ap-northeast-1' });
let cachedAuth: { value: string; fetchedAt: number } | null = null;

async function getExpectedAuth(): Promise<string> {
  if (cachedAuth && Date.now() - cachedAuth.fetchedAt < AUTH_CACHE_TTL_MS) {
    return cachedAuth.value;
  }
  const result = await ssm.send(
    new GetParameterCommand({ Name: AUTH_PARAM_NAME, WithDecryption: true })
  );
  const value = result.Parameter?.Value ?? '';
  cachedAuth = { value, fetchedAt: Date.now() };
  return value;
}

// 長さが異なる場合も比較時間を揃えるため、常に自分自身とのtimingSafeEqualを1回挟む
function safeCompare(provided: string, expected: string): boolean {
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) {
    crypto.timingSafeEqual(a, a);
    return false;
  }
  return crypto.timingSafeEqual(a, b);
}

function unauthorized(): Response {
  return new Response('Authentication required', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Zer0-CryptoBot Stats"' },
  });
}

export const onRequest = defineMiddleware(async (context, next) => {
  if (context.url.pathname.startsWith(PRIVATE_PATH_PREFIX)) {
    const authHeader = context.request.headers.get('authorization') || '';
    const expected = await getExpectedAuth();
    let ok = false;
    if (expected && authHeader.startsWith('Basic ')) {
      const provided = Buffer.from(authHeader.slice(6), 'base64').toString('utf-8');
      ok = safeCompare(provided, expected);
    }
    if (!ok) {
      return unauthorized();
    }
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString('base64').replace(/=+$/, '');
  context.locals.cspNonce = nonce;

  const response = await next();

  // Set CSP dynamically so the nonce can be included.
  // CloudFront ResponseHeadersPolicy has Override:false for CSP,
  // so this header takes precedence over the static fallback.
  response.headers.set('Cache-Control', 'no-store');

  if (context.url.pathname.startsWith(PRIVATE_PATH_PREFIX)) {
    // 検索エンジン・キャッシュへの露出を避ける
    response.headers.set('X-Robots-Tag', 'noindex, nofollow');
  }

  response.headers.set(
    'Content-Security-Policy',
    [
      "default-src 'self'",
      "connect-src 'self'",
      `script-src 'self' 'nonce-${nonce}'`,
      `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
      `font-src https://fonts.gstatic.com`,
      "img-src 'self' data:",
      "object-src 'none'",
      "base-uri 'self'",
    ].join('; ')
  );

  return response;
});
