const ROOT = new URL(self.registration.scope);
const CACHE_PREFIX = 'fieldwork-' + ROOT.pathname + '-';
const CACHE = CACHE_PREFIX + 'v2';
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(['./', './index.html', './icon.svg', './manifest.webmanifest']))); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith(CACHE_PREFIX) && k !== CACHE).map(k => caches.delete(k))))); });
self.addEventListener('fetch', event => { const url = new URL(event.request.url); if (event.request.method !== 'GET' || url.origin !== ROOT.origin || !url.pathname.startsWith(ROOT.pathname) || url.pathname.includes('/api/')) return; event.respondWith(fetch(event.request).then(response => { if(response.ok) { const copy = response.clone(); event.waitUntil(caches.open(CACHE).then(cache=>cache.put(event.request, copy))); } return response; }).catch(async () => (await caches.match(event.request)) || (event.request.mode === 'navigate' ? await caches.match('./index.html') : Response.error()))); });
