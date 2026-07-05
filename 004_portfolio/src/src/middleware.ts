import { defineMiddleware } from 'astro:middleware';
import crypto from 'node:crypto';
import { SSMClient, GetParameterCommand } from '@aws-sdk/client-ssm';

// 全てのインラインスクリプトは nonce={Astro.locals.cspNonce} を付与済み
// （Nav.astro / BaseLayout.astro / templates/index.astro(ja,en) / templates/[category]/index.astro(ja,en)）。
// 2026-07-03以前はハッシュ全件を手動計算してハードコードする方式だったが、
// スクリプト変更のたびに複数箇所のハッシュ再計算が必要で壊れやすかったため、
// nonceベースに統一した（ハッシュはlambda.mjsのSTATIC_CSP側にのみ残す。
// そちらはインラインスクリプトを持たないAPIルート用のフォールバックのため実質未使用）。

// ── 管理者モード（2026-07-04）───────────────────────────────────────────
// 007のadminトークン方式を踏襲。?admin=<トークン> に一度アクセスすると
// Cookieに365日保存され、以降はサイト全体でAstro.locals.isAdminがtrueになる。
// /ja/cryptobot-stats はisAdminがfalseなら401（Nav.astroの管理者リンクも同条件で非表示）。
// ?admin=off でCookie削除。SSM SecureStringはトークン文字列そのものを保持する
// （旧Basic認証時代の "user:pass" 形式から移行済み）。
const PRIVATE_PATH_PREFIX = '/ja/cryptobot-stats';
const AUTH_PARAM_NAME = '/Zer0/Portfolio/cryptobot-stats-auth';
const AUTH_CACHE_TTL_MS = 5 * 60 * 1000;
const ADMIN_COOKIE_NAME = 'admin_auth';
const ADMIN_COOKIE_MAX_AGE_S = 60 * 60 * 24 * 365; // 365日

const ssm = new SSMClient({ region: process.env.AWS_REGION || 'ap-northeast-1' });
let cachedToken: { value: string; fetchedAt: number } | null = null;

async function getExpectedToken(): Promise<string> {
  if (cachedToken && Date.now() - cachedToken.fetchedAt < AUTH_CACHE_TTL_MS) {
    return cachedToken.value;
  }
  const result = await ssm.send(
    new GetParameterCommand({ Name: AUTH_PARAM_NAME, WithDecryption: true })
  );
  const value = result.Parameter?.Value ?? '';
  cachedToken = { value, fetchedAt: Date.now() };
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

function parseCookies(header: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of header.split(';')) {
    const eq = part.indexOf('=');
    if (eq === -1) continue;
    out[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
  }
  return out;
}

function buildCookie(value: string, maxAgeSeconds: number): string {
  // 2026-07-05: SameSite=Strictだと、リンク経由（メモ・チャット等からのアクセス）の
  // トップレベルナビゲーションでCookieが送信されないモバイルブラウザがあり、
  // 「指定URLでアクセスしたのに認証されない」報告の原因となっていた。
  // Laxでもクロスサイトのサブリソース・POST等には送信されないため、
  // このページ（閲覧専用の管理者トグル）用途では十分な安全性を保ったまま解消できる。
  return `${ADMIN_COOKIE_NAME}=${value}; Max-Age=${maxAgeSeconds}; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

export const onRequest = defineMiddleware(async (context, next) => {
  const cookies = parseCookies(context.request.headers.get('cookie') || '');
  const expected = await getExpectedToken();

  let isAdmin = !!expected && !!cookies[ADMIN_COOKIE_NAME] && safeCompare(cookies[ADMIN_COOKIE_NAME], expected);
  let setCookie: string | null = null;

  // ?admin=<トークン> / ?admin=off はどのページでも受け付ける
  const adminParam = context.url.searchParams.get('admin');
  const isValidTokenParam = !!adminParam && adminParam !== 'off' && !!expected && safeCompare(adminParam, expected);

  if (adminParam === 'off') {
    isAdmin = false;
    setCookie = buildCookie('', 0);
  } else if (isValidTokenParam) {
    isAdmin = true;
    setCookie = buildCookie(expected, ADMIN_COOKIE_MAX_AGE_S);
  }

  // 2026-07-05 Fableレビューで推奨（案B）: 保護ページに有効なトークン付きでアクセスした場合は
  // リダイレクトせずこのリクエストの中で直接描画する。モバイルブラウザでCookieの往復
  // （保存・再送信）が信頼できず「指定URLでアクセスしたのに見れない」報告があったための対応。
  // Cookie自体（下記SameSite=Lax）は利便性向上のため引き続き発行するが、
  // ブックマークした保護ページ直指定のURLはCookieの成否に一切依存せず毎回確実に動作する。
  const skipRedirectForDirectAccess = isValidTokenParam && context.url.pathname.startsWith(PRIVATE_PATH_PREFIX);

  if (adminParam !== null && !skipRedirectForDirectAccess) {
    // トークンをURL・ブラウザ履歴に残さないよう、クエリを外してリダイレクト
    const cleanUrl = new URL(context.url);
    cleanUrl.searchParams.delete('admin');
    const redirect = new Response(null, {
      status: 302,
      headers: { Location: cleanUrl.pathname + cleanUrl.search },
    });
    if (setCookie) redirect.headers.set('Set-Cookie', setCookie);
    return redirect;
  }

  if (context.url.pathname.startsWith(PRIVATE_PATH_PREFIX) && !isAdmin) {
    return new Response('管理者専用ページです。管理者URLでアクセスしてください。', { status: 401 });
  }

  context.locals.isAdmin = isAdmin;

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

  // 直接描画（skipRedirectForDirectAccess）の場合はリダイレクトを経由しないため、
  // ここで実レスポンスにCookieを付与する（append: 他のSet-Cookieを上書きしない）。
  if (setCookie && skipRedirectForDirectAccess) {
    response.headers.append('Set-Cookie', setCookie);
  }

  // 保護ページのURLにトークンが残るケース（skipRedirectForDirectAccess時）に備え、
  // 外部リソース（Google Fonts等）へのリクエストでクエリ文字列が漏れないよう明示する
  // （モダンブラウザのデフォルトでも安全だが念のため）。
  response.headers.set('Referrer-Policy', 'same-origin');

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
