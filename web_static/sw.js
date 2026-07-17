const CACHE = "ptos-v2";
const ASSETS = ["/", "/static/manifest.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(ASSETS))
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  var url = new URL(e.request.url);
  if (url.pathname === "/api/events") return;
  e.respondWith(
    caches.match(e.request).then((r) => r || fetch(e.request))
  );
});
