# 南平一中动漫社官网

> 以热爱为名 · 共创二次元家园

[![Vercel](https://img.shields.io/badge/部署-Vercel-000000?logo=vercel)](https://www.nanyi-anime-club.top)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask)](https://flask.palletsprojects.com)
[![Tests](https://img.shields.io/badge/tests-77_passing-brightgreen)](#)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase)](https://supabase.com)

南平一中动漫社的官方网站 —— 集社团展示、互动交流、资源分享于一体的校内平台。项目由社团成员独立开发并持续维护。

🔗 **在线访问**：[https://www.nanyi-anime-club.top](https://www.nanyi-anime-club.top)

---

## ✨ 功能亮点

### 面向社员
- **用户系统**：注册 / 登录 / 个人主页 / 头像上传 / 密码修改
- **留言板**：支持嵌套回复，自动关联用户头像
- **活动展示**：按时间排序的活动列表
- **照片墙**：按活动分类展示珍贵历史照片
- **番剧资源**：社员推荐 → 管理员审核 → 公开下载链接
- **社员名单**：查看所有注册社员
- **萌战系统**：完整的海选 → 小组赛 → 淘汰赛 → 最终排名流程

### 面向管理
- **活动管理**：增删改活动，支持活动关联照片的级联删除
- **照片墙管理**：批量上传/删除活动照片，存储至 Supabase Storage
- **番剧审核**：审核社员推荐的番剧资源，或手动添加
- **用户管理**：查看社员列表，切换运营/站长身份，删除用户
- **权限体系**：站长（最高权限）和运营（日常管理）双角色分离

---

## 🛠 技术栈

| 分类 | 技术 |
|------|------|
| 后端框架 | Python 3.12 + Flask 3.0 |
| 数据库 | PostgreSQL（Supabase） |
| 文件存储 | Supabase Storage |
| 部署平台 | Vercel |
| 前端 | HTML + CSS + Jinja2 模板 |
| 测试框架 | Pytest + Coverage |
| 图像处理 | Pillow |

---

## 🚀 本地运行

### 1. 克隆仓库
```bash
git clone https://github.com/N-zihan/anime-club.git
cd anime-club
2. 创建虚拟环境
bash
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# 或 .venv\Scripts\activate    # Windows
3. 安装依赖
bash
pip install -r requirements.txt
4. 配置环境变量
在项目根目录创建 .env 文件：

env
# 必填
DATABASE_URL=postgresql://user:password@host:port/dbname
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
SECRET_KEY=your-secret-key-32-characters-min
GROUP_VERIFICATION_CODE=社团QQ群号
# 可选
APP_VERSION=dev

5. 运行应用
bash
python run.py
访问 http://127.0.0.1:5000

6. 运行测试
bash
pytest -v

🧪 测试覆盖
项目包含 77 个测试用例，覆盖：
用户认证（注册/登录/注销/删号）
数据库模型（User/Contest/Candidate/Vote 等）
萌战引擎（阶段计算/晋级逻辑/最终排名）
公共页面（所有路由的访问性）
管理后台（权限/功能）
投票功能（海选/小组赛/淘汰赛）

📝 许可证
本项目仅供学习交流使用，如需引用请注明来源。

💬 反馈与建议
如果你发现 Bug 或有功能建议，欢迎在网站的 留言板 中反馈，或联系站长。

Made with ❤️ by 南平一中动漫社