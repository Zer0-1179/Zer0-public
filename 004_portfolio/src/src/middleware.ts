import { defineMiddleware } from 'astro:middleware';
import crypto from 'node:crypto';

// SHA-256 hashes of all inlined scripts. Recompute after any script change:
//   node --input-type=module -e "..."  (see scripts/hash-nav-script.mjs pattern)
const SCRIPT_HASHES = [
  "'sha256-UYCtDDmMoDHvTISYj6fW+GkhSw+u880Y62A+oJ+zftk='", // Nav.astro
  "'sha256-2mZe1216qSfXhWjWW7LgH/iaMAXbV60fBI2HwiXJGpM='", // BaseLayout font
  "'sha256-zcbm4FJaWWCwAgnJ0yCOTvXZkKYxVl/I4ORIl10vIXA='", // ja/templates/index
  "'sha256-1oCXA/UY7N5q7PEDNBJJHymj0ckybtkBsJ9dAnnhQ9s='", // en/templates/index
  "'sha256-iHmrsk23cnkNmaXiQoIcxqwOp2m/wDYT0TyA8jixISs='", // ja/templates/[category]
  "'sha256-30cQFjkZyd3AUeYigBcz8I/DwYAu0c3KpNoS//mOLuI='", // en/templates/[category]
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
