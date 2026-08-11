import type { APIRoute } from 'astro';
import { projects } from '../data/projects';
import { getCategoriesWithTemplates } from '../data/templates';

export const GET: APIRoute = ({ site }) => {
  const base = site ? site.origin : 'https://www.zer0-infra.com';
  const langs = ['ja', 'en'];

  const staticPaths = ['', '/about', '/projects', '/articles', '/contact', '/templates'];
  const projectPaths = projects.map((p) => `/projects/${p.slug}`);
  const categoryPaths = getCategoriesWithTemplates().map((c) => `/templates/${c.slug}`);

  const allPaths = [...staticPaths, ...projectPaths, ...categoryPaths];

  const urls = langs.flatMap((lang) =>
    allPaths.map((path) => `${base}/${lang}${path}/`)
  );

  // 2026-07-05 Fableブラッシュアップ: lastmodが無いとcrawlerが再クロール頻度を判断しづらい。
  // ページ単位の実際の更新日追跡は無いため、デプロイ日を全URL共通のlastmodとして付与する。
  // 2026-08-11: 手動更新運用が37日間放置され形骸化していたため、astro.config.mjsの
  // vite.define(__BUILD_DATE__)でビルド時刻を焼き込む方式に変更（手動更新不要）。
  const lastmod = __BUILD_DATE__;

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((url) => `  <url>\n    <loc>${url}</loc>\n    <lastmod>${lastmod}</lastmod>\n  </url>`).join('\n')}
</urlset>`;

  return new Response(xml, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
