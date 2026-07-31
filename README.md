[![Vercel](https://img.shields.io/badge/部署-Vercel-000000?logo=vercel)](https://www.nanyi-anime-club.top)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask)](https://flask.palletsprojects.com)
[![Tests](https://img.shields.io/badge/tests-77_passing-brightgreen)](#)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase)](https://supabase.com)

# 南平一中动漫社官网

> 以热爱为名 · 共创二次元家园

南平一中动漫社官方网站，集社团展示、互动交流、资源分享于一体的校内平台。

🔗 在线访问：https://www.nanyi-anime-club.top

## 功能亮点

- 用户系统：注册 / 登录 / 个人主页 / 头像上传 / 密码修改
- 留言板：嵌套回复，自动关联头像
- 活动展示：按时间排序
- 照片墙：活动照片分类展示
- 番剧资源：社员推荐 → 管理员审核 → 公开链接
- 社员名单：查看所有注册社员
- 萌战系统：海选 → 小组赛 → 淘汰赛 → 最终排名
- 管理后台：站长 / 运营双角色权限分离

## 技术栈

Python 3.12 + Flask 3.0 / PostgreSQL (Supabase) / Supabase Storage / Vercel / HTML + CSS + Jinja2 / Pytest

## 本地运行

```bash
git clone https://github.com/N-zihan/anime-club.git
cd anime-club
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# .venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

创建 .env 文件：

```env
DATABASE_URL=postgresql://...
SUPABASE_URL=https://...
SUPABASE_KEY=...
SECRET_KEY=...
GROUP_VERIFICATION_CODE=社团QQ群号
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

77 个测试用例全部通过。

许可证

本项目仅供学习交流使用，如需引用请注明来源。

Made with ❤️ by 南平一中动漫社
