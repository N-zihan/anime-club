// 缓存的版本号——每次更新缓存时修改这个版本号
const CACHE_VERSION = 'v1';
const CACHE_NAME = `anime-club-${CACHE_VERSION}`;

// 需要缓存的资源（只加静态页面和样式文件）
const urlsToCache = [
  '/',
  '/home',
  '/about',
  '/activities',
  '/gallery',
  '/board',
  '/anime_resources',
  '/members',
  '/contest_center',
  '/static/css/style.css',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png',
  '/static/favicon.ico'
];

// 安装 Service Worker —— 缓存核心资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('缓存资源');
        return cache.addAll(urlsToCache);
      })
  );
});

// 激活 Service Worker —— 清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME && cacheName.startsWith('anime-club-')) {
            console.log('删除旧缓存:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

// 拦截请求 —— 先缓存，再网络
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      })
  );
});
