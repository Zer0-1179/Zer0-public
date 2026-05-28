import serverlessHttp from 'serverless-http';
import { handler as astroMiddleware } from './dist/server/entry.mjs';
import express from 'express';

const app = express();
app.disable('x-powered-by');

const GITHUB_RAW_BASE =
  'https://raw.githubusercontent.com/Zer0-1179/Zer0-public/main/templates';

// CFnテンプレートのダウンロードプロキシ
// Astro middleware モードでは serverless-http 経由でカスタムヘッダーが失われるため Express で直接処理する
app.get('/api/templates/:filename', async (req, res) => {
  const { filename } = req.params;
  if (!filename || !/^cfn-[a-z0-9-]+\.yaml$/.test(filename)) {
    return res.status(404).send('Not Found');
  }
  try {
    const response = await fetch(`${GITHUB_RAW_BASE}/${filename}`);
    if (!response.ok) return res.status(404).send('Not Found');
    const content = await response.text();
    res.setHeader('Content-Type', 'application/octet-stream');
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    res.send(content);
  } catch {
    res.status(500).send('Internal Server Error');
  }
});

// Astro i18n redirect (prefixDefaultLocale:true) loses Location header via serverless-http
app.get('/', (req, res) => res.redirect(302, '/ja/'));

app.use(astroMiddleware);

export const handler = serverlessHttp(app);
