// Keep this version in sync with the asset query strings in index.html. This
// forces installed clients to discard cached authorization and app scripts.
const CACHE = "household-ledger-mobile-v112";
const asset = path => path + "?v=112";
const SHELL = ["/", ...[
  "/style.css", "/mobile.css", "/app.js", "/mobile.js", "/github-login.js",
  "/gitee-login.js", "/appearance.js", "/manifest.webmanifest", "/icon.svg",
  "/apple-touch-icon.png", "/icon-192.png", "/icon-512.png",
].map(asset)];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  event.respondWith(fetch(request).then(response => {
    if (response.ok && (url.pathname === "/" || SHELL.some(path => new URL(path, self.location.origin).pathname === url.pathname))) {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(request, copy));
    }
    return response;
  }).catch(async () => {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.mode === "navigate") return caches.match("/");
    return Response.error();
  }));
});
