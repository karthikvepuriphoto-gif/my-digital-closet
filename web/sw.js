const CACHE = "closet-shell-v7";
const SHELL = [
  "./",
  "./index.html",
  "./privacy.html",
  "./styles.css",
  "./app.js",
  "./closet.js",
  "./db.js",
  "./vision.js",
  "./runner.js",
  "./scan-session.js",
  "./native-scan.js",
  "./favicon.ico",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
  "./icons/apple-touch-icon.png",
  "./samples/coat.webp",
  "./samples/shirt.webp",
  "./samples/shoes.webp",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(event.request);
    const network = fetch(event.request)
      .then((response) => {
        if (response.ok) cache.put(event.request, response.clone());
        return response;
      })
      .catch(() => cached);
    return cached || network;
  })());
});
