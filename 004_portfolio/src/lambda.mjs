import serverlessHttp from 'serverless-http';
import { handler as astroMiddleware } from './dist/server/entry.mjs';
import express from 'express';

const app = express();
app.disable('x-powered-by');
app.use((req, res, next) => {
  const originalSend = res.send.bind(res);
  res.send = (body) => {
    if (res.get('Content-Type')?.startsWith('text/plain') && typeof body === 'string' && body.trimStart().startsWith('<')) {
      res.set('Content-Type', 'text/html; charset=utf-8');
    }
    return originalSend(body);
  };
  next();
});
app.use(astroMiddleware);

export const handler = serverlessHttp(app);
