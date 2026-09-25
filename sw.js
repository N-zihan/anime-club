// 缓存的版本号——每次更新缓存时修改这个版本号
const CACHE_VERSION = 'v1';
const CACHE_STATIC = `anime-club-static-${CACHE_VERSION}`;
const CACHE_DYNAMIC = `anime-club-dynamic-${CACHE_VERSION}`;

// 只预缓存静态资源（动态页面走 network-first）
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
                    if (name.startsWith('anime-club-') &&
                        name !== CACHE_STATIC &&
                        name !== CACHE_DYNAMIC) {
                        return caches.delete(name);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// 拦截请求
self.addEventListener('fetch', (event) => {
    const { request } = event;

    // 只处理 GET
    if (request.method !== 'GET') return;

    const url = new URL(request.url);

    // 只处理同源
    if (url.origin !== self.location.origin) return;

    // 静态资源：cache-first
    if (url.pathname.startsWith('/static/') || url.pathname === '/favicon.ico') {
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
        return;
    }

    // 动态页面：network-first，失败时 fallback 到缓存
    // 动态页面：network-first，失败时 fallback 到缓存，再失败给离线提示
    event.respondWith(
        fetch(request).then((response) => {
            if (response.ok) {
                const clone = response.clone();
                caches.open(CACHE_DYNAMIC).then((cache) => cache.put(request, clone));
            }
            return response;
        }).catch(() => caches.match(request).then(
            (cached) => cached || new Response(
                '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
                + '<meta name="viewport" content="width=device-width,initial-scale=1">'
                + '<title>离线</title></head><body style="font-family:sans-serif;'
                + 'text-align:center;padding:80px 20px;color:#334155;">'
                + '<h1>暂时离线</h1><p>网络好像断了，恢复后刷新页面即可。</p>'
                + '</body></html>',
                {
                    status: 503,
                    headers: { 'Content-Type': 'text/html; charset=utf-8' },
                }
            )
        ))
    );
});
