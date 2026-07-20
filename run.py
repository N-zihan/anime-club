"""
南平一中动漫社官网 · 项目启动入口
====================================

本文件是整个应用的启动入口。
它通过导入 create_app() 工厂函数创建 Flask 应用实例，
并在 __main__ 中启动开发服务器。

使用方式：
    python run.py

生产环境建议使用 gunicorn 或其他 WSGI 服务器启动：
    gunicorn run:app

注意：开发模式下 debug=False，如需调试请手动修改。
"""

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
