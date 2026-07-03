import { defineMiddleware } from 'astro:middleware';
import crypto from 'node:crypto';

// 全てのインラインスクリプトは nonce={Astro.locals.cspNonce} を付与済み
// （Nav.astro / BaseLayout.astro / templates/index.astro(ja,en) / templates/[category]/index.astro(ja,en)）。
// 2026-07-03以前はハッシュ全件を手動計算してハードコードする方式だったが、
// スクリプト変更のたびに複数箇所のハッシュ再計算が必要で壊れやすかったため、
// nonceベースに統一した（ハッシュはlambda.mjsのSTATIC_CSP側にのみ残す。
// そちらはインラインスクリプトを持たないAPIルート用のフォールバックのため実質未使用）。
export const onRequest = defineMiddleware(async (context, next) => {
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64').replace(/=+$/, '');
  context.locals.cspNonce = nonce;

  const response = await next();

  // Set CSP dynamically so the nonce can be included.
  // CloudFront ResponseHeadersPolicy has Override:false for CSP,
  // so this header takes precedence over the static fallback.
  response.headers.set('Cache-Control', 'no-store');

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
