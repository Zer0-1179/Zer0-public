import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'server',

  adapter: node({ mode: 'middleware' }),

  vite: {
    plugins: [tailwindcss()],
    // sitemap.xmlのlastmod用。ビルド実行時刻を焼き込む（デプロイのたびに自動更新される）。
    define: {
      __BUILD_DATE__: JSON.stringify(new Date().toISOString().slice(0, 10)),
    },
  },

  site: process.env.SITE_URL || 'http://localhost:4321',

  i18n: {
    defaultLocale: 'ja',
    locales: ['ja', 'en'],
    routing: {
      prefixDefaultLocale: true,
    },
  },

  build: {
    format: 'directory',
  },
});
