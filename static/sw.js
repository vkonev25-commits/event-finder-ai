const CACHE_NAME = 'tourevents-v2';
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/style.css',
  '/static/app.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];

// Установка и предварительное кеширование статики
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
});

// Стратегия "сеть сначала, иначе кеш" для тайлов и данных
self.addEventListener('fetch', event => {
  // Для API и внешних карт — только сеть (не кешируем)
  if (event.request.url.includes('/api/')) {
    return;
  }
  // Для тайлов OpenStreetMap — network first, fallback to cache
  if (event.request.url.includes('tile.openstreetmap.org')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        return fetch(event.request).then(response => {
          // Кладём в кеш свежий ответ
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, responseClone));
          return response;
        }).catch(() => cached);
      })
    );
    return;
  }
  // Для всего остального — стандартный cache-first
  event.respondWith(
    caches.match(event.request).then(response => response || fetch(event.request))
  );
});

// Удаление старых кешей при активации
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      );
    })
  );
});
