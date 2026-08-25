// Service worker — базовая установка приложения + кэш app shell, чтобы страницу
// загрузки фотоотчёта можно было открыть повторно даже без связи (черновик всё
// равно копится в IndexedDB через offline-report.js, это независимый механизм).
const CACHE_NAME = 'furniture-app-shell-v1';
const APP_SHELL = [
    '/',
    '/static/css/app.css',
    '/static/manifest.json',
    '/static/icons/icon-192.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {}),
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) => Promise.all(
            names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)),
        )),
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return; // POST (отправка отчёта) не кэшируем и не перехватываем

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                const copy = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
                return response;
            })
            .catch(() => caches.match(event.request)),
    );
});

// Web Push — уведомление от самого приложения (см. apps/notifications).
self.addEventListener('push', (event) => {
    let payload = { title: 'Сборка мебели', body: '' };
    try {
        payload = { ...payload, ...event.data.json() };
    } catch (e) {
        payload.body = event.data ? event.data.text() : '';
    }
    event.waitUntil(
        self.registration.showNotification(payload.title, {
            body: payload.body,
            icon: '/static/icons/icon-192.png',
            badge: '/static/icons/icon-192.png',
            data: { url: payload.url || '/' },
        }),
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
            for (const client of clients) {
                if (client.url.includes(self.location.origin) && 'focus' in client) {
                    client.navigate(url);
                    return client.focus();
                }
            }
            return self.clients.openWindow(url);
        }),
    );
});
