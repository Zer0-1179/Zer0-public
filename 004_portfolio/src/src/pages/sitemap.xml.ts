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

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((url) => `  <url>\n    <loc>${url}</loc>\n  </url>`).join('\n')}
</urlset>`;

  return new Response(xml, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
