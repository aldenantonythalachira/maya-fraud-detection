const VERSION = "maya-v4-shell-1";
const SHELL = [
  "/app/",
  "/product-static/product.css",
  "/product-static/customer.js",
  "/product-static/icon.svg",
];
self.addEventListener("install", (e) =>
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL))),
);
self.addEventListener("activate", (e) =>
  e.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("maya-v4-shell-") && k !== VERSION)
            .map((k) => caches.delete(k)),
        ),
      ),
  ),
);
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (
    e.request.method !== "GET" ||
    u.origin !== location.origin ||
    u.pathname.startsWith("/v1/")
  )
    return;
  if (SHELL.includes(u.pathname))
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
