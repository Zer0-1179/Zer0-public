import serverlessHttp from 'serverless-http';
import { handler as astroMiddleware } from './dist/server/entry.mjs';
import express from 'express';

const app = express();
app.disable('x-powered-by');
app.use((req, res, next) => {
  const origSetHeader = res.setHeader;
  res.setHeader = function(name, value) {
    if (name.toLowerCase() === 'content-type' && String(value).startsWith('text/plain')) {
      value = 'text/html; charset=utf-8';
    }
    return origSetHeader.call(this, name, value);
  };
  next();
});
app.use(astroMiddleware);

export const handler = serverlessHttp(app);
