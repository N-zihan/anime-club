[![Vercel](https://img.shields.io/badge/部署-Vercel-000000?logo=vercel)](https://www.nanyi-anime-club.top)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask)](https://flask.palletsprojects.com)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase)](https://supabase.com)
[![Tests](https://img.shields.io/badge/tests-79_passing-brightgreen)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

# 南平一中动漫社官网

> 以热爱为名 · 共创二次元家园

> 一个由16岁高中生Nzihan开发、学长LLLinV指点的社团网站项目

南平一中动漫社官方网站，集社团展示、互动交流、资源分享与线上赛事于一体的校内平台

🔗 在线访问：https://www.nanyi-anime-club.top

## 功能亮点

### 用户系统
- 注册 / 登录 / 登出 / 账号注销
- 个人主页（头像、留言、推荐番剧）
- 头像上传（支持 jpg/png/gif，自动压缩至 200×200）
- 用户名修改、密码修改
- 邮箱绑定（用于密码找回）

### 留言板
- 社员自由发言，支持嵌套回复（回复主留言 / 回复某条回复）
- 自动关联用户头像
- 留言与回复时间显示北京时间

### 活动展示
- 按时间排序展示社团活动
- 管理员可在后台增删改活动

### 照片墙
- 活动照片分类展示
- 支持“往期活动照片”独立展示
- 图片自动压缩（1200×1200，品质85）
- 存储于 Supabase Storage

### 番剧资源
- 社员推荐番剧链接 + 提取码
- 管理员审核 → 公开显示
- 支持管理员手动添加

### 社员名单
- 展示所有注册社员
- 点击头像进入个人主页

### 萌战系统（核心特色）
社团内部线上赛事引擎，支持完整的“海选 → 小组赛 → 淘汰赛 → 最终排名”流程。

| 阶段                        | 赛制 | 晋级规则 |
|-----------------------------|------|----------|
| **提名期**(5天)             | 每人最多提名 5 个角色，管理员审核 | 进入海选池 |
| **海选**(4天投票 + 1天公示) | 每人每组 15 票，最多投 5 个角色，单角色 ≤ 3 票 | 男女各取前 32 名 |
| **小组赛**(3轮 × (4+1)天)   | 8 组 × 4 人，单循环积分制（胜+3 / 平+1 / 负+0） | 每组前 2 名，共 16 人 |
| **淘汰赛**(4轮 × (4+1)天)   | 16 强 → 8 强 → 4 强 → 决赛，1v1 单败淘汰 | 小组第一 vs 小组第二 + 同组回避 |
| **最终排名**                | 按淘汰轮次排序生成完整排名 | 冠军 / 亚军 / 四强 / 八强 / 十六强 |

> 平票处理：淘汰赛平票时比较海选阶段总票数(按 candidate.id 匹配，避免重名误判)
>
> 自动推进：所有阶段按预设时间自动切换，无需人工干预。

### 管理后台
- **站长**：全部管理权限(活动/照片/番剧/用户/留言/赛事)
- **运营**：内容管理权限(活动/照片/番剧/赛事)

## 技术栈

| 类别 | 技术 |
|------|------|
| 后端框架 | Python 3.12 + Flask 3.0 |
| ORM | SQLAlchemy 2.0 |
| 数据库 | PostgreSQL（Supabase） |
| 文件存储 | Supabase Storage |
| 图片处理 | Pillow |
| 前端 | HTML + CSS + Jinja2 |
| 测试 | Pytest（79 个测试用例） |
| 部署 | Vercel |
| 认证 | Session-based + Werkzeug 密码哈希 |
| 安全 | CSRFProtect（Flask-WTF） |


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
├── tests/ # Pytest测试套件(79个用例)
│ ├── conftest.py # 测试配置与 fixtures
│ ├── test_auth.py # 认证模块测试
│ ├── test_admin.py # 管理后台测试
│ ├── test_public.py # 公共页面测试
│ ├── test_user.py # 用户中心测试
│ ├── test_api.py # API 端点测试
│ ├── test_models.py # 数据模型测试
│ └── test_contest_engine.py # 萌战引擎测试
│
├── .env # 环境变量模板(自行创建)
├── requirements.txt # Python 依赖
├── LICENSE # 许可证
├── pytest.ini # 测试配置
├── run.py # 应用启动入口
├── README.md # 项目说明
├── vercel.json # vercel配置
└── .gitignore # Git 忽略规则
```

## 本地运行
```bash
git clone https://github.com/N-zihan/anime-club.git
cd anime-club
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
.venv/Scripts/activate         # Windows
pip install -r requirements.txt
```

创建 .env 文件：
```env
DATABASE_URL=postgresql://...
GROUP_VERIFICATION_CODE=社团群号
SUPABASE_URL=https://...
SUPABASE_KEY=Supabase service role key
SECRET_KEY=自创一个密码
SUPABASE_ANON_KEY=Supabase的anon_key
CLUB_NAME=社团名字

# SMTP 邮件配置(用于发送验证码和重置链接)
MAIL_USERNAME=你的QQ邮箱(建议额外注册一个)
MAIL_PASSWORD=SMTP邮箱验证码
```

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

### Supabase 数据库

1. 在 [Supabase](https://supabase.com) 创建一个新项目
2. 获取以下信息：
   - **Project URL** → 填写到 `SUPABASE_URL`
   - **Database Password** → 数据库密码
   - **SQL Editor** 中执行以下语句创建表（或直接使用项目中的 `models.py` 通过 SQLAlchemy 自动创建）：

```sql
-- 项目启动后会自动创建表，也可以手动执行
-- 建议先运行 python run.py，让 SQLAlchemy 自动建表
```
获取 SUPABASE_KEY(Settings → API → service_role secret)

### Vercel 部署

在 Vercel 点击 Add New → Project

导入你的 GitHub 仓库

在 Environment Variables 中填入所有.env变量(见上方.env模板)

点击 Deploy

项目已包含 vercel.json 配置文件，Vercel 会自动识别 Python Flask 应用。

部署完成后，Vercel 会自动生成一个域名(可绑定自定义域名)

## 项目状态
- 核心功能完整
- 79个测试用例全部通过
- 已部署至生产环境
- 已开源（MIT License）

## 许可证
本项目采用 MIT License 开源。

你可以自由地使用、修改、分发本项目的代码，但需保留原始版权声明。详情请见 LICENSE 文件。

*Made with ❤️ by 南平一中动漫社*
