const CACHE = 'zer0-touring-v9';

self.addEventListener('install', e => { self.skipWaiting(); });

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API・外部ドメイン → SW素通し（キャッシュしない）
  if (url.pathname.startsWith('/api/') || url.hostname !== self.location.hostname) return;

  // /_astro/* と /icons/* は不変ハッシュ付きなのでキャッシュファースト
  if (url.pathname.startsWith('/_astro/') || url.pathname.startsWith('/icons/')) {
    e.respondWith(
      caches.match(e.request).then(hit =>
        hit ?? fetch(e.request).then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone()));
          return res;
        })
      )
    );
    return;
  }

  // index.html / manifest.json → ネットワーク優先（常に最新を取得）
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone()));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
