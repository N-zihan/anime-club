# 南平一中动漫社官网

> 以热爱为名 · 共创二次元家园

这是南平一中动漫社的官方网站，一个集社团展示、互动交流、资源分享于一体的校内平台。项目由社团成员独立开发并持续维护。

🔗 在线访问：[https://www.nanyi-anime-club.top](https://www.nanyi-anime-club.top)

---

## ✨ 功能亮点

- **用户系统**：注册 / 登录 / 游客体验 / 个人主页 / 头像上传 / 密码修改
- **留言板**：社员交流、回复、自动关联头像
- **活动展示**：活动列表、按时间排序
- **照片墙**：活动照片分类展示（支持管理员批量上传）
- **番剧资源**：社员推荐 → 管理员审核 → 公开下载链接
- **社员名单**：查看所有注册社员
- **管理后台**：活动管理、照片管理、番剧审核、用户管理（运营/站长权限分离）

---

## 技术栈

| 分类     | 技术                     |
|----------|--------------------------|
| 后端框架 | Python + Flask           |
| 数据库   | Supabase (PostgreSQL)    |
| 文件存储 | Supabase Storage         |
| 部署平台 | Vercel                   |
| 前端     | HTML + CSS + Jinja2 模板 |

---

## 🚀 本地运行

如果你想在本地测试或二次开发，可以按照以下步骤：

1. **克隆仓库**
   ```bash
   git clone https://github.com/N-zihan/anime-club.git
   cd anime-club

创建虚拟环境

bash python -m venv .venv source .venv/bin/activate # Windows: .venv\Scripts\activate 安装依赖

bash pip install -r requirements.txt 配置环境变量 在项目根目录创建 .env 文件，填入以下内容（替换为你的实际值）：

env DATABASE_URL=postgresql://... SUPABASE_URL=https://... SUPABASE_KEY=... ADMIN_PASSWORD=你的管理员密码
GROUP_VERIFICATION_CODE=社团QQ群号 SECRET_KEY=你的Flask密钥 运行应用

bash python run.py 打开浏览器访问 http://127.0.0.1:5000

👥 运营团队 站长：BlueArchive

运营：待定（可在后台设置）

📌 后续计划 社团通知公告系统

活动报名功能

社员私信（可选）

📝 许可证 本项目仅供学习交流使用，如需引用请注明来源。

💬 反馈与建议 如果你发现 Bug 或有功能建议，欢迎在网站的 留言板 中反馈，或联系站长。

Made with ❤️ by 南平一中动漫社