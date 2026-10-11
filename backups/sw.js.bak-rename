// Sentinel UI V3 — Service Worker
const CACHE = 'sentinel-v3';
const ASSETS = ['./sentinel_ui_v3.html', './manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  // Network first for API calls, cache first for assets
  if (e.request.url.includes('localhost:8765') || e.request.url.includes('localhost:11434')) {
    return; // Let API calls go straight through
  }
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
