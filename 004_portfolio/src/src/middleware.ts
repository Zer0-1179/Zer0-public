import { defineMiddleware } from 'astro:middleware';
import crypto from 'node:crypto';

// SHA-256 hashes of all inlined scripts. Recompute after any script change:
//   node --input-type=module -e "..."  (see scripts/hash-nav-script.mjs pattern)
const SCRIPT_HASHES = [
  "'sha256-UYCtDDmMoDHvTISYj6fW+GkhSw+u880Y62A+oJ+zftk='", // Nav.astro
  "'sha256-2mZe1216qSfXhWjWW7LgH/iaMAXbV60fBI2HwiXJGpM='", // BaseLayout font
  "'sha256-nBkbTataBdvlgdlOt3Vr4oQNmEXlYljqccazFHtA2hA='", // ja/templates/index
  "'sha256-BbdfFf3SSABC2MwBjewRJNNNcEXAwOv3cfNu4BwCln0='", // en/templates/index
  "'sha256-x1Br5NBxUF3JwdXihhDg0g0e6FgOtXi9m7c1kV32WKA='", // ja/templates/[category]
  "'sha256-rJYFB/xhPE/QUzeEC6WdbzuXBcVe5qlhGG89I/C9OC8='", // en/templates/[category]
].join(' ');

export const onRequest = defineMiddleware(async (context, next) => {
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64').replace(/=+$/, '');
  context.locals.cspNonce = nonce;

  const response = await next();

  // Set CSP dynamically so the nonce can be included.
  // CloudFront ResponseHeadersPolicy has Override:false for CSP,
  // so this header takes precedence over the static fallback.
  response.headers.set(
    'Content-Security-Policy',
    [
      "default-src 'self'",
      "connect-src 'self'",
      `script-src 'self' 'nonce-${nonce}' ${SCRIPT_HASHES}`,
      `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
      `font-src https://fonts.gstatic.com`,
      "img-src 'self' data:",
      "object-src 'none'",
      "base-uri 'self'",
    ].join('; ')
  );

  return response;
});
