<div align="center">

# 动漫社全功能网站

[![Vercel](https://img.shields.io/badge/Deployments-Vercel-000000?logo=vercel)](https://www.nanyi-anime-club.top)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask)](https://flask.palletsprojects.com)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase)](https://supabase.com)
[![Python application](https://github.com/N-zihan/anime-club/actions/workflows/python-app.yml/badge.svg)](https://github.com/N-zihan/anime-club/actions/workflows/python-app.yml)
[![Pylint](https://github.com/N-zihan/anime-club/actions/workflows/pylint.yml/badge.svg)](https://github.com/N-zihan/anime-club/actions/workflows/pylint.yml)
[![CodeQL Advanced](https://github.com/N-zihan/anime-club/actions/workflows/codeql.yml/badge.svg)](https://github.com/N-zihan/anime-club/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 建站即用 · 开箱即改

动漫社全功能网站，集社团展示、互动交流、资源分享、线上赛事于一体

***在线访问***：[www.nanyi-anime-club.top](https://www.nanyi-anime-club.top)

</div>

## 功能概览

| 功能         | 说明                                               |
|--------------|----------------------------------------------------|
| 用户系统     | 注册、登录、邮箱绑定、密码重置、头像上传           |
| 留言板       | 支持嵌套回复，关联用户头像                         |
| 番剧资源     | 社员推荐 → 管理员审核 → 公开显示                   |
| 照片墙       | 活动照片分类展示，存储于 Supabase Storage          |
| **萌战系统** | 线上赛事引擎：提名 → 海选 → 小组赛 → 淘汰赛 → 冠军 |
| 管理后台     | 站长 / 运营双角色权限分离                          |

## 萌战系统

> 社团内部赛事引擎，男女分组独立比赛

| 阶段                                         | 赛制                                   | 晋级                  |
|----------------------------------------------|----------------------------------------|-----------------------|
| **提名期**（5天）                            | 每人提名 5 个角色                      | 进入海选池            |
| **海选**（5天）                              | 每人 15 票，最多投 5 人，单角色 ≤ 3 票 | 男女各前 32 名        |
| **小组赛**（3×5天）                          | 8 组 × 4 人，单循环积分制              | 每组前 2 名，共 16 人 |
| **淘汰赛**（4×5天）                          | 16 强 → 8 强 → 4 强 → 决赛             | 冠军 + 最终排名       |
| **注**: 除提名期外，每五天的最后一天为公示期 |


> 平票处理：淘汰赛平票时比较海选总票数
> 自动推进：所有阶段按预设时间自动切换

## 技术栈

| 类别       | 技术                              |
|------------|-----------------------------------|
| 后端框架   | Python 3.14.4 + Flask 3.0         |
| ORM        | SQLAlchemy 2.0                    |
| 数据库     | PostgreSQL(Supabase)              |
| 文件存储   | Supabase Storage                  |
| 图片处理   | Pillow                            |
| 前端       | HTML + CSS + Jinja2               |
| 测试       | Pytest(92 个测试用例)             |
| 部署       | Vercel                            |
| 认证       | Session-based + Werkzeug 密码哈希 |
| 安全       | CSRFProtect(Flask-WTF)            |
| AI 解说    | SiliconFlow API(DeepSeek-V3)      |

> AI 解说功能依赖 SiliconFlow API，需自行申请 API Key


## 项目结构
```text
动漫社网站/
├── app/ # 应用核心代码
│ ├── __init__.py # Flask 应用工厂(含CSRF/Session安全配置)
│ ├── admin.py # 管理后台(站长/运营双角色)
│ ├── auth.py # 用户认证(注册/登录/密码重置/邮箱验证)
│ ├── contest_engine.py # 萌战引擎核心(赛程/晋级/排名)
│ ├── models.py # 数据库模型(13张表)
│ ├── public.py # 公共页面路由
│ ├── user.py # 用户中心(个人设置/头像/主页)
│ └── utils.py # 工具函数(Supabase/图片压缩)
│
├── templates/ # Jinja2前端模板(42个页面)
├── static/ # 静态资源
│ ├── avatars/ # 默认头像
│ └── css/ # 全局样式
│
├── tests/ # Pytest测试套件(92个用例)
│ ├── conftest.py # 测试配置与 fixtures
│ ├── test_auth.py # 认证模块测试
│ ├── test_admin.py # 管理后台测试
│ ├── test_public.py # 公共页面测试
│ ├── test_user.py # 用户中心测试
│ ├── test_api.py # API 端点测试
│ ├── test_models.py # 数据模型测试
│ └── test_contest_engine.py # 萌战引擎测试
│
├── .env # 环境变量(自行创建)
├── requirements.txt # Python 依赖
├── LICENSE # 许可证
├── pytest.ini # 测试配置
├── run.py # 应用启动入口
├── README.md # 项目说明
├── vercel.json # vercel配置
└── .gitignore # Git 忽略规则
```

## 快速开始

```bash
git clone https://github.com/N-zihan/anime-club.git
cd anime-club
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# .venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

创建 .env 文件:
```env
DATABASE_URL=postgresql://...
GROUP_VERIFICATION_CODE=社团群号
SUPABASE_URL=https://...
SUPABASE_KEY=Settings → API → service_role secret # 仅供后端
SECRET_KEY=自创一个密码
SUPABASE_ANON_KEY=Settings → API → anon public # 用于前端
CLUB_NAME=社团名字 # 默认 动漫社
APP_VERSION=版本号 # 默认 dev

# AI模型配置
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.siliconflow.cn/v1 
AI_MODEL=deepseek-ai/DeepSeek-V3
AI_CACHE_ENABLED=true
AI_CACHE_TTL=3600     

# SMTP 邮件配置(用于发送验证码和重置链接)
SMTP_HOST= # 默认smtp.qq.com
SMTP_PORT= # 默认465
SMTP_USE_SSL=true # 默认true开启
MAIL_USERNAME=你的QQ邮箱 # 建议额外注册一个
MAIL_PASSWORD=SMTP邮箱授权码
```
> API_key从[siliconflow](https://cloud.siliconflow.cn)获取，需付费

运行：
```bash
python run.py
```
访问 http://127.0.0.1:5000

测试：
```bash
pytest -v
```

## 部署准备

准备好把网站部署到公网了？只需要两个免费服务：Supabase（数据库）和 Vercel（网站托管）

### Supabase：创建数据库

1. 访问 [Supabase](https://supabase.com) 注册账号，点击 **New project**
2. 填写项目名称、设置数据库密码，区域推荐选择 **Mumbai** 或 **Singapore**（国内访问更快）
3. 等待项目创建完成（约 2-3 分钟）

### 获取连接信息

项目创建完成后，在 Dashboard 页面顶部点击 **Connect** 按钮，会弹出一个连接面板，先选择 **Direct Connection string** ，里面包含了所有你需要的信息：

- **Session pooler（推荐）**：端口 `6543`，适用于 Vercel 等 Serverless 环境，支持最多 200 个并发连接
- **Direct connection**：端口 `5432`，直连数据库，限额 60 个连接

在 **Connection string** 区域找到 `URI` 格式的连接串，复制后替换密码即可得到 `DATABASE_URL`。

> 推荐使用 Transaction pooler（端口 6543），避免 Vercel 函数并发时占用过多数据库连接。

### 获取 Project URL 和 API Keys

1. 进入项目 Dashboard
2. 左侧菜单点击 **Integrations**
3. 选择 **Data API**
4. 在 Overview 页面即可看到 **API URL**（这就是 Project URL）

格式为：`https://xxxxxxxxxxxxx.supabase.co`

API Keys 在同一页面的 **Project API keys** 区域获取：

- **`anon` public**（或新版项目的 `Publishable key`）→ 填到 `SUPABASE_ANON_KEY`
- **`service_role` secret**（或新版项目的 `Secret key`）→ 填到 `SUPABASE_KEY`

> `service_role` 密钥权限极高，仅供后端使用，切勿泄露或提交到代码仓库。

### Vercel：部署网站

1. 创建仓库，推送代码至你的仓库
2. 访问 [Vercel](https://vercel.com)，用 GitHub 登录
3. 点击 **Add New → Project**，选择你的仓库导入
4. 在 **Environment Variables** 中添加环境变量（参考上面的 `.env` 模板）
5. 点击 **Deploy**，等待 1-2 分钟即可

> Vercel 会自动识别 Flask 应用，无需额外配置。部署后可以在侧边菜单栏 Environment Variables 中随时增删改环境变量

> 域名请前往域名供应商注册，推荐前往 [NameSilo](https://www.namesilo.com)（海外供应商，注册无需备案，若需备案，vercel不再适用，请使用国内服务器）
>
> 如果暂时不打算部署到公网，也可以只在本地运行，跳过这一步。run.py 启动后访问 http://127.0.0.1:5000 即可

> Supabase 和 Vercel 的免费计划足够支撑小型社团网站，赛事期间不会产生额外费用

## 项目状态
- 核心功能完整
- 92个测试用例全部通过
- 已部署至生产环境

## 许可证
本项目采用 MIT License 开源

你可以自由地使用、修改、分发本项目的代码，但需保留原始版权声明。详情请见 LICENSE 文件

*Made with ❤️ by 南平一中动漫社*
