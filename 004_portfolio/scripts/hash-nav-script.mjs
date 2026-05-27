#!/usr/bin/env node
// Compute the SHA-256 hash of the inlined Nav script from the Astro build output.
// Run after `npm run build` when Nav.astro's <script> block has changed.
// Then update NAV_SCRIPT_HASH in src/middleware.ts.
import crypto from 'node:crypto';
import fs from 'node:fs';
import { glob } from 'node:fs/promises';
import path from 'node:path';

const distDir = new URL('../src/dist/server/chunks/', import.meta.url);
const files = fs.readdirSync(distDir).filter(f => f.startsWith('server_'));

let found = false;
for (const file of files) {
  const content = fs.readFileSync(path.join(distDir.pathname, file), 'utf8');
  const match = content.match(/"inlinedScripts":\[\["[^"]*","((?:[^"\\]|\\.)*)"\]\]/);
  if (match) {
    const script = JSON.parse('"' + match[1] + '"');
    const hash = crypto.createHash('sha256').update(script, 'utf8').digest('base64');
    console.log(`SHA-256: ${hash}`);
    console.log(`CSP value: 'sha256-${hash}'`);
    console.log(`\nUpdate NAV_SCRIPT_HASH in src/src/middleware.ts to:\n  "'sha256-${hash}'"`);
    found = true;
    break;
  }
}

if (!found) {
  console.log('No inlined scripts found. The Nav script may have become an external file (no update needed).');
}
