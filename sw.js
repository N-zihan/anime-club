// 缓存的版本号——每次更新缓存时修改这个版本号
const CACHE_VERSION = 'v1';
const CACHE_STATIC = `anime-club-static-${CACHE_VERSION}`;

// 只预缓存静态资源
const STATIC_URLS = [
    '/static/css/style.css',
    '/static/images/icon-192.png',
    '/static/images/icon-512.png',
    '/static/favicon.ico',
];

// 安装 —— 预缓存静态资源，并立即跳过等待
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_STATIC).then((cache) => cache.addAll(STATIC_URLS))
    );
    self.skipWaiting();
});

// 激活 —— 清理旧版本缓存，立即接管页面
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) => {
            return Promise.all(
                names.map((name) => {
                    if (name.startsWith('anime-club-') && name !== CACHE_STATIC) {
                        return caches.delete(name);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// 拦截请求：只处理静态资源，动态页面一律交给浏览器
self.addEventListener('fetch', (event) => {
    const { request } = event;

    // 只处理 GET
    if (request.method !== 'GET') return;

    const url = new URL(request.url);

    // 只处理同源
    if (url.origin !== self.location.origin) return;

    // 只有静态资源走 SW；其他一律放过，让浏览器自己处理
    if (!url.pathname.startsWith('/static/') && url.pathname !== '/favicon.ico') {
        return;
    }

    event.respondWith(
        caches.match(request).then((cached) => {
            if (cached) return cached;
            return fetch(request).then((response) => {
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_STATIC).then((cache) => cache.put(request, clone));
                }
                return response;
            });
        })
    );
});
