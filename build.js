const fs = require('fs');
const path = require('path');

// 读取 sw.js
const swPath = path.join(__dirname, 'static', 'sw.js');
let swContent = fs.readFileSync(swPath, 'utf8');

// 用当前时间替换版本号
const timestamp = Date.now();
swContent = swContent.replace(
  /const CACHE_VERSION = '.*';/,
  `const CACHE_VERSION = '${timestamp}';`
);

fs.writeFileSync(swPath, swContent);
console.log(`sw.js 版本号已更新为 ${timestamp}`);
