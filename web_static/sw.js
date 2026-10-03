// Retired service worker: drop any caches the old cache-first worker made and
// unregister. Keep it at /static/sw.js (pinned no-cache) for a release or two
// so browsers with the old worker registered can pick up this self-destruct.
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((key) => caches.delete(key)));
    } catch (err) {}
    try {
      await self.registration.unregister();
    } catch (err) {}
    try {
      const clients = await self.clients.matchAll({ type: "window" });
      clients.forEach((client) => client.navigate(client.url));
    } catch (err) {}
  })());
});
