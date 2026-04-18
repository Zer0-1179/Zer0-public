import serverlessHttp from 'serverless-http';
import { handler as astroMiddleware } from './dist/server/entry.mjs';
import express from 'express';

const app = express();
app.disable('x-powered-by');
app.use(astroMiddleware);

export const handler = serverlessHttp(app);
