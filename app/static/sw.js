self.addEventListener('install', (event) => {
  event.waitUntil(caches.open('roomfit-v1').then((cache) => cache.addAll(['/','/static/styles.css'])));
});

self.addEventListener('fetch', (event) => {
  event.respondWith(caches.match(event.request).then((resp) => resp || fetch(event.request)));
});
