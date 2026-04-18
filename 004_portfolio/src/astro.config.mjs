import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'server',

  adapter: node({ mode: 'middleware' }),

  vite: {
    plugins: [tailwindcss()],
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
