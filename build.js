const fs = require('fs');
const path = require('path');

const swPath = path.join(__dirname, 'static', 'sw.js');
let swContent = fs.readFileSync(swPath, 'utf8');

// 从环境变量读取版本号，如果没有则用时间戳
const version = process.env.APP_VERSION || Date.now().toString();

swContent = swContent.replace(
  /const CACHE_VERSION = '.*';/,
  `const CACHE_VERSION = '${version}';`
);

fs.writeFileSync(swPath, swContent);
console.log(`sw.js 版本号已更新为 ${version}`);
