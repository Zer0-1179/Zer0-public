import serverlessHttp from 'serverless-http';
import { handler as astroMiddleware } from './dist/server/entry.mjs';
import express from 'express';

const app = express();
app.disable('x-powered-by');

// Astro i18n redirect (prefixDefaultLocale:true) loses Location header via serverless-http
app.get('/', (req, res) => res.redirect(302, '/ja/'));

app.use(astroMiddleware);

export const handler = serverlessHttp(app);
