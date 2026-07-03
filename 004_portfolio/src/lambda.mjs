import serverlessHttp from 'serverless-http';
import { handler as astroMiddleware } from './dist/server/entry.mjs';
import express from 'express';
import JSZip from 'jszip';

const app = express();
app.disable('x-powered-by');

const GITHUB_RAW_BASE =
  'https://raw.githubusercontent.com/Zer0-1179/Zer0-public/main/templates';

// { difficulty: { category: [...files] } }
const CATEGORY_FILES = {
  advanced: {
    network:    ['cfn-vpc.yaml', 'cfn-igw.yaml', 'cfn-nat.yaml', 'cfn-security-group.yaml', 'cfn-security-group-ingress.yaml', 'cfn-security-group-egress.yaml', 'cfn-alb.yaml', 'cfn-nlb.yaml'],
    compute:    ['cfn-ecr.yaml', 'cfn-ecs-cluster.yaml', 'cfn-ecs-service.yaml', 'cfn-lambda.yaml', 'cfn-ec2.yaml'],
    storage:    ['cfn-s3.yaml', 'cfn-efs.yaml', 'cfn-ebs.yaml'],
    database:   ['cfn-dynamodb.yaml', 'cfn-rds.yaml', 'cfn-elasticache.yaml'],
    security:   ['cfn-kms.yaml', 'cfn-iam-role.yaml'],
    messaging:  ['cfn-sqs.yaml', 'cfn-sns.yaml', 'cfn-eventbridge.yaml'],
    monitoring:  ['cfn-cw-logs.yaml', 'cfn-cw-alarm-ec2.yaml', 'cfn-cw-alarm-rds.yaml', 'cfn-cw-alarm-efs.yaml', 'cfn-cw-alarm-lambda.yaml', 'cfn-cw-alarm-sqs.yaml', 'cfn-cw-alarm-alb.yaml'],
    automation:  ['cfn-cw-alarm-auto-update.yaml'],
  },
  beginner: {
    network:    ['cfn-vpc-basic.yaml', 'cfn-igw-basic.yaml', 'cfn-nat-basic.yaml', 'cfn-security-group-basic.yaml', 'cfn-security-group-ingress-basic.yaml', 'cfn-security-group-egress-basic.yaml', 'cfn-alb-basic.yaml', 'cfn-nlb-basic.yaml'],
    compute:    ['cfn-ecr-basic.yaml', 'cfn-ecs-cluster-basic.yaml', 'cfn-ecs-service-basic.yaml', 'cfn-lambda-basic.yaml', 'cfn-ec2-basic.yaml'],
    storage:    ['cfn-s3-basic.yaml', 'cfn-efs-basic.yaml', 'cfn-ebs-basic.yaml'],
    database:   ['cfn-dynamodb-basic.yaml', 'cfn-rds-basic.yaml', 'cfn-elasticache-basic.yaml'],
    security:   ['cfn-kms-basic.yaml', 'cfn-iam-role-basic.yaml'],
    messaging:  ['cfn-sqs-basic.yaml', 'cfn-sns-basic.yaml', 'cfn-eventbridge-basic.yaml'],
    monitoring:  ['cfn-cw-logs-basic.yaml', 'cfn-cw-alarm-ec2-basic.yaml', 'cfn-cw-alarm-rds-basic.yaml', 'cfn-cw-alarm-efs-basic.yaml', 'cfn-cw-alarm-lambda-basic.yaml', 'cfn-cw-alarm-sqs-basic.yaml', 'cfn-cw-alarm-alb-basic.yaml'],
    automation:  ['cfn-cw-alarm-auto-update-basic.yaml'],
  },
};

// Reverse lookup: filename → { diff, cat }
const FILE_META = {};
for (const [diff, cats] of Object.entries(CATEGORY_FILES)) {
  for (const [cat, files] of Object.entries(cats)) {
    for (const f of files) FILE_META[f] = { diff, cat };
  }
}

// ZIP一括ダウンロード: /api/templates/download/all.zip, /advanced.zip, /beginner.zip, /{category}.zip
app.get('/api/templates/download/:zipname', async (req, res) => {
  const { zipname } = req.params;
  let entries; // [{ diff, cat, filename }]
  let downloadName;

  if (zipname === 'all.zip') {
    entries = Object.entries(CATEGORY_FILES).flatMap(([diff, cats]) =>
      Object.entries(cats).flatMap(([cat, files]) => files.map(f => ({ diff, cat, filename: f })))
    );
    downloadName = 'cfn-templates-all.zip';
  } else if (zipname === 'advanced.zip' || zipname === 'beginner.zip') {
    const diff = zipname.slice(0, -4);
    entries = Object.entries(CATEGORY_FILES[diff]).flatMap(([cat, files]) =>
      files.map(f => ({ diff, cat, filename: f }))
    );
    downloadName = `cfn-templates-${diff}.zip`;
  } else if (/^[a-z]+\.zip$/.test(zipname)) {
    const cat = zipname.slice(0, -4);
    const matched = Object.entries(CATEGORY_FILES).flatMap(([diff, cats]) =>
      (cats[cat] || []).map(f => ({ diff, cat, filename: f }))
    );
    if (!matched.length) return res.status(404).send('Not Found');
    entries = matched;
    downloadName = `cfn-templates-${cat}.zip`;
  } else {
    return res.status(404).send('Not Found');
  }

  try {
    const zip = new JSZip();
    const results = await Promise.allSettled(entries.map(async ({ diff, cat, filename }) => {
      const r = await fetch(`${GITHUB_RAW_BASE}/${diff}/${cat}/${filename}`, { signal: AbortSignal.timeout(10000) });
      if (!r.ok) throw new Error(`${filename}: HTTP ${r.status}`);
      const zipPath = zipname === 'all.zip' ? `${diff}/${cat}/${filename}` : `${cat}/${filename}`;
      zip.file(zipPath, await r.text());
    }));
    const failed = results.filter(r => r.status === 'rejected');
    if (failed.length === entries.length) return res.status(502).send('Failed to fetch templates');
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
  const meta = FILE_META[filename];
  if (!meta) return res.status(404).send('Not Found');
  try {
    const response = await fetch(`${GITHUB_RAW_BASE}/${meta.diff}/${meta.cat}/${filename}`, { signal: AbortSignal.timeout(10000) });
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

// CSP fallback: Astro middleware's Response headers need writeHead to be intercepted
// to reach serverless-http. The STATIC_CSP is injected only when Astro doesn't set one
// (e.g., the ZIP/YAML download routes and the "/" redirect below, none of which render
// inline scripts). For page routes, Astro's dynamic nonce-based CSP (src/middleware.ts)
// takes precedence and is the one actually gating inline script execution.
const STATIC_CSP = [
  "default-src 'self'",
  "connect-src 'self'",
  [
    "script-src 'self'",
    "'sha256-2mZe1216qSfXhWjWW7LgH/iaMAXbV60fBI2HwiXJGpM='", // BaseLayout font
    "'sha256-UYCtDDmMoDHvTISYj6fW+GkhSw+u880Y62A+oJ+zftk='", // Nav menu
    "'sha256-KXUDQAuXOeqRrd1aNG0JF4S5VtF/LiYF4RsHdHaWN1k='", // ja/templates/index
    "'sha256-1DhTENB/zpG3cKR7goiDvncDxumSdUUwJ02mq45dVno='", // en/templates/index
    "'sha256-cWbZQz7qqZr7bU3ee4onPOv2dX9PBo/h26P+y0O1bzo='", // ja/templates/[category]（2026-07-03 file-row click修正で更新）
    "'sha256-DgX2pBSQucJ4N60pwee4TwGFAbw6IESlTzfW5Z/g3Ws='", // en/templates/[category]（2026-07-03 file-row click修正で更新）
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
