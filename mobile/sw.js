// Mission Control — Service Worker
// Cache shell assets; network-first for API; cache-first for statics.

const CACHE_NAME = 'mc-shell-v2';
const SHELL_ASSETS = [
  '/mobile/',
  '/mobile/index.html',
  '/mobile/manifest.json',
];

// ── Install: cache shell assets ──
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_ASSETS))
  );
});

// ── Activate: clean old caches ──
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ── Fetch strategy ──
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Network-first for API calls
  if (url.pathname.startsWith('/mobile/api/') || url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }

  // Cache-first for static assets (icons, sw.js itself, manifest)
  if (
    url.pathname.startsWith('/mobile/icons/') ||
    url.pathname === '/mobile/manifest.json' ||
    url.pathname === '/mobile/sw.js'
  ) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
    return;
  }

  // Network-first with cache fallback for everything else
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

// ── Push notifications ──
self.addEventListener('push', event => {
  let data = { title: 'Mission Control', body: 'New event' };
  try { data = event.data ? event.data.json() : data; } catch(e) {}
  event.waitUntil(
    self.registration.showNotification(data.title || 'Mission Control', {
      body:    data.body || '',
      icon:    '/mobile/icons/icon.svg',
      badge:   '/mobile/icons/icon.svg',
      tag:     data.tag || 'mc-alert',
      data:    data,
      vibrate: [200, 100, 200],
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then(clients => {
      for (const client of clients) {
        if (client.url.includes('/mobile') && 'focus' in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow('/mobile/');
    })
  );
});
