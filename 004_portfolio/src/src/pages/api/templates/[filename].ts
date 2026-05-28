import type { APIRoute } from 'astro';

const GITHUB_RAW_BASE =
  'https://raw.githubusercontent.com/Zer0-1179/Zer0-public/main/templates';

export const GET: APIRoute = async ({ params }) => {
  const { filename } = params;

  if (!filename || !/^cfn-[a-z0-9-]+\.yaml$/.test(filename)) {
    return new Response('Not Found', { status: 404 });
  }

  const res = await fetch(`${GITHUB_RAW_BASE}/${filename}`);
  if (!res.ok) {
    return new Response('Not Found', { status: 404 });
  }

  const content = await res.text();
  return new Response(content, {
    headers: {
      'Content-Type': 'application/octet-stream',
      'Content-Disposition': `attachment; filename="${filename}"`,
    },
  });
};
