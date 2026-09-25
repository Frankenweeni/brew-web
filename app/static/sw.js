// Brew Web service worker
// Keeps a small offline cache of static assets so the installed app has an
// icon/shell immediately. Pages themselves (batches, recipes, etc.) always
// go to the network, since they're authenticated and change often.

const CACHE_NAME = 'brew-web-shell-v1';
const SHELL_ASSETS = [
  '/static/style.css',
  '/static/calculators.css',
  '/static/favicon.ico',
  '/static/images/bw-logo.png',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Only handle simple GET requests; let everything else (POST forms, etc.)
  // pass straight through untouched.
  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);

  // Static assets: cache-first, so the installed shell (logo/icons/css)
  // shows up instantly and works offline.
  if (SHELL_ASSETS.some((path) => url.pathname === path)) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request))
    );
    return;
  }

  // Everything else (batch pages, recipes, calculators, login, etc.) is
  // dynamic/authenticated content — always go to the network.
});
