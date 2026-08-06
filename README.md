[![Vercel](https://img.shields.io/badge/部署-Vercel-000000?logo=vercel)](https://www.nanyi-anime-club.top)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask)](https://flask.palletsprojects.com)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase)](https://supabase.com)
[![Tests](https://img.shields.io/badge/tests-79_passing-brightgreen)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

# 南平一中动漫社官网

> 以热爱为名 · 共创二次元家园

> 这是一个由16岁高中生Nzihan开发、学长LLLinV指点的社团网站项目，欢迎 star 和交流

南平一中动漫社官方网站，集社团展示、互动交流、资源分享于一体的校内平台。

🔗 在线访问：https://www.nanyi-anime-club.top

## 功能亮点

* 用户系统：注册 / 登录 / 个人主页 / 头像上传 / 密码修改
* 留言板：嵌套回复，自动关联头像
* 活动展示：按时间排序
* 照片墙：活动照片分类展示
* 番剧资源：社员推荐 → 管理员审核 → 公开链接
* 社员名单：查看所有注册社员
* 萌战系统：海选 → 小组赛 → 淘汰赛 → 最终排名
* 管理后台：站长 / 运营双角色权限分离

## 技术栈

Python 3.14 + Flask 3.0 / PostgreSQL (Supabase) / Supabase Storage / Vercel / HTML + CSS + Jinja2 / Pytest

## 项目结构
<pre>
动漫社网站/
├── app/ # 应用核心代码
│ ├── init.py # Flask 应用工厂
│ ├── admin.py # 管理后台路由（站长/运营）
│ ├── auth.py # 用户认证（注册/登录/密码重置）
│ ├── contest_engine.py # 萌战引擎核心（海选→小组赛→淘汰赛）
│ ├── models.py # 数据库模型（13张表）
│ ├── public.py # 公共页面路由
│ ├── user.py # 用户中心（个人设置/头像/主页）
│ └── utils.py # 工具函数（Supabase/图片压缩）
│
├── templates/ # Jinja2 前端模板（42个页面）
├── static/ # 静态资源
│ ├── avatars/ # 默认头像
│ └── css/ # 全局样式
│
├── tests/ # Pytest 测试套件（77个用例）
│ ├── conftest.py # 测试配置与 fixtures
│ ├── test_auth.py # 认证模块测试
│ ├── test_admin.py # 管理后台测试
│ ├── test_public.py # 公共页面测试
│ ├── test_user.py # 用户中心测试
│ ├── test_api.py # API 端点测试
│ ├── test_models.py # 数据模型测试
│ └── test_contest_engine.py # 萌战引擎测试
│
├── .venv/ # Python 虚拟环境（不提交）
├── .env.example # 环境变量模板
├── requirements.txt # Python 依赖
├── run.py # 应用启动入口
├── README.md # 项目说明
├── vercel.json # vercel配置
└── .gitignore # Git 忽略规则
</pre>

## 本地运行

```bash
git clone https://github.com/N-zihan/anime-club.git
cd anime-club
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# .venv\\Scripts\\activate       # Windows
pip install -r requirements.txt
```

创建 .env 文件：

```env
DATABASE\_URL=postgresql://...
SUPABASE\_URL=https://...
SUPABASE\_KEY=...
SECRET\_KEY=...
GROUP\_VERIFICATION\_CODE=社团QQ群号
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

测试覆盖

79 个测试用例全部通过。

许可证

本项目仅供学习交流使用，如需引用请注明来源，使用需自行配置环境变量。

Made with ❤️ by 南平一中动漫社

