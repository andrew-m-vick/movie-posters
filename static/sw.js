// CINEDATA Service Worker
// Caches the app shell so it loads instantly and works offline.

const CACHE = 'cinedata-v7';
const SHELL = [
  '/',
  'https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&family=DM+Mono:wght@400;500&family=Playfair+Display:ital,wght@0,400;0,700;1,400&display=swap',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // Let TMDB API, tile requests, and curated IMAX JSON files always go to the network
  // (so manual updates to imax-films / imax-theaters / imax-now-playing land immediately)
  const url = e.request.url;
  if (url.includes('api.themoviedb.org') || url.includes('basemaps.cartocdn') ||
      url.includes('nominatim.openstreetmap') || url.includes('router.project-osrm') ||
      url.includes('/static/imax-')) {
    return;
  }
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
