import os

from dotenv import load_dotenv
from flask import Flask, session, request, redirect, url_for

from .admin import admin_bp
from .auth import auth_bp
from .models import db
from .public import public_bp, page_not_found, internal_server_error, forbidden
from .user import user_bp
from .utils import supabase

load_dotenv()


def create_app():
    # 获取项目根目录（run.py 所在目录）
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static'),
        static_url_path='/static'  # 修复点
    )
    app.secret_key = os.getenv('SECRET_KEY', '20090929nzh')

    # 数据库配置
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)

    # 注册错误处理器（直接从 public 模块导入）
    app.register_error_handler(404, page_not_found)
    app.register_error_handler(500, internal_server_error)
    app.register_error_handler(403, forbidden)

    # 登录拦截器
    @app.before_request
    def require_login():
        public_routes = ['auth.login', 'auth.register', 'static', 'public.splash']
        if not session.get('user_id') and request.endpoint not in public_routes and request.endpoint != 'static':
            return redirect(url_for('auth.login'))

    return app
