/// <reference path="../.astro/types.d.ts" />

declare namespace App {
  interface Locals {
    cspNonce: string;
    isAdmin: boolean;
  }
}

// astro.config.mjs の vite.define で焼き込まれるビルド日付（sitemap.xml.ts の lastmod用）
declare const __BUILD_DATE__: string;