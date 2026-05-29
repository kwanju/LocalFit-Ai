// Minimal app-shell service worker (ADR-009: PWA from the start).
// Network-first for navigation so the SPA always boots fresh when online;
// cache fallback keeps "add to home screen" usable offline. API/WS calls are
// never cached — coaching is realtime and local-only (ADR-002).
const CACHE = "localfit-shell-v1";
const SHELL = ["/", "/index.html", "/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // Don't intercept backend traffic — must hit the live server.
  if (["/health", "/sessions", "/routines", "/onboarding", "/ws"].some((p) => url.pathname.startsWith(p))) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/index.html")));
    return;
  }

  event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
});
