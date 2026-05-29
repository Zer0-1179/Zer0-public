import serverlessHttp from 'serverless-http';
import { handler as astroMiddleware } from './dist/server/entry.mjs';
import express from 'express';
import JSZip from 'jszip';

const app = express();
app.disable('x-powered-by');

const GITHUB_RAW_BASE =
  'https://raw.githubusercontent.com/Zer0-1179/Zer0-public/main/templates';

const CATEGORY_FILES = {
  network:    ['cfn-vpc.yaml', 'cfn-igw.yaml', 'cfn-nat.yaml', 'cfn-security-group.yaml', 'cfn-security-group-ingress.yaml', 'cfn-security-group-egress.yaml', 'cfn-alb.yaml', 'cfn-nlb.yaml'],
  compute:    ['cfn-ecr.yaml', 'cfn-ecs-cluster.yaml', 'cfn-ecs-service.yaml', 'cfn-lambda.yaml', 'cfn-ec2.yaml'],
  storage:    ['cfn-s3.yaml', 'cfn-efs.yaml', 'cfn-ebs.yaml'],
  database:   ['cfn-dynamodb.yaml', 'cfn-rds.yaml'],
  security:   ['cfn-kms.yaml', 'cfn-iam-role.yaml'],
  messaging:  ['cfn-sqs.yaml'],
  monitoring: ['cfn-cw-logs.yaml'],
};

// ZIP一括ダウンロード: /api/templates/download/all.zip or /{category}.zip
app.get('/api/templates/download/:zipname', async (req, res) => {
  const { zipname } = req.params;
  let filenames;
  let downloadName;

  if (zipname === 'all.zip') {
    filenames = Object.values(CATEGORY_FILES).flat();
    downloadName = 'cfn-templates-all.zip';
  } else if (/^[a-z]+\.zip$/.test(zipname)) {
    const cat = zipname.slice(0, -4);
    if (!CATEGORY_FILES[cat]) return res.status(404).send('Not Found');
    filenames = CATEGORY_FILES[cat];
    downloadName = `cfn-templates-${cat}.zip`;
  } else {
    return res.status(404).send('Not Found');
  }

  try {
    const zip = new JSZip();
    await Promise.all(filenames.map(async (fn) => {
      const r = await fetch(`${GITHUB_RAW_BASE}/${fn}`);
      if (!r.ok) throw new Error(`fetch failed: ${fn}`);
      zip.file(fn, await r.text());
    }));
    const buf = await zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE', compressionOptions: { level: 6 } });
    res.status(200)
      .set('Content-Type', 'application/zip')
      .set('Content-Disposition', `attachment; filename="${downloadName}"`)
      .set('Content-Length', buf.length);
    res.end(buf);
  } catch {
    res.status(500).send('Internal Server Error');
  }
});

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

// CSP: Astro middleware sets headers on its Response object but those don't reach API GW.
// Intercept writeHead to inject the static hash-based CSP into the actual HTTP response.
const STATIC_CSP = [
  "default-src 'self'",
  "connect-src 'self'",
  [
    "script-src 'self'",
    "'sha256-2mZe1216qSfXhWjWW7LgH/iaMAXbV60fBI2HwiXJGpM='", // BaseLayout font
    "'sha256-UYCtDDmMoDHvTISYj6fW+GkhSw+u880Y62A+oJ+zftk='", // Nav menu
    "'sha256-nBkbTataBdvlgdlOt3Vr4oQNmEXlYljqccazFHtA2hA='", // ja/templates/index
    "'sha256-BbdfFf3SSABC2MwBjewRJNNNcEXAwOv3cfNu4BwCln0='", // en/templates/index
    "'sha256-x1Br5NBxUF3JwdXihhDg0g0e6FgOtXi9m7c1kV32WKA='", // ja/templates/[category]
    "'sha256-rJYFB/xhPE/QUzeEC6WdbzuXBcVe5qlhGG89I/C9OC8='", // en/templates/[category]
  ].join(' '),
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src https://fonts.gstatic.com",
  "img-src 'self' data:",
  "object-src 'none'",
  "base-uri 'self'",
].join('; ');

app.use((req, res, next) => {
  const origWriteHead = res.writeHead.bind(res);
  res.writeHead = function(statusCode, ...args) {
    if (!res.getHeader('Content-Security-Policy')) {
      res.setHeader('Content-Security-Policy', STATIC_CSP);
    }
    return origWriteHead(statusCode, ...args);
  };
  next();
});

app.use(astroMiddleware);

export const handler = serverlessHttp(app, {
  binary: ['application/zip'],
});
