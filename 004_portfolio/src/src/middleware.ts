import { defineMiddleware } from 'astro:middleware';
import crypto from 'node:crypto';

// SHA-256 hash of the minified Nav hamburger script (inlined by Astro's SSR build).
// Update this value by running: node scripts/hash-nav-script.mjs
// after changing src/components/Nav.astro's <script> block.
const NAV_SCRIPT_HASH = "'sha256-UYCtDDmMoDHvTISYj6fW+GkhSw+u880Y62A+oJ+zftk='";

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
      `script-src 'self' 'nonce-${nonce}' ${NAV_SCRIPT_HASH}`,
      `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
      `font-src https://fonts.gstatic.com`,
      "img-src 'self' data:",
      "object-src 'none'",
      "base-uri 'self'",
    ].join('; ')
  );

  return response;
});
