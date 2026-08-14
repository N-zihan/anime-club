"""
南平一中动漫社官网 · Flask 应用工厂模块
============================================

本模块是整个网站的核心入口，负责创建和配置 Flask 应用实例。
它通过 create_app() 工厂函数完成以下工作：

1. 加载环境变量（数据库连接、密钥、版本号等）
2. 初始化 SQLAlchemy 数据库连接
3. 注册所有蓝图模块（认证、公共、用户、管理后台）
4. 注册全局错误处理器（400/403/404/405/413/500）
5. 设置登录拦截器（未登录用户自动跳转至登录页）
6. 注入模板全局变量（版本号、用户权限标识）

这种工厂模式使得应用可以被多次实例化，便于测试和扩展。
"""

import os

from dotenv import load_dotenv
from flask import Flask, session, request, redirect, url_for, flash
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError

from .admin import admin_bp
from .auth import auth_bp
from .models import db
from .public import public_bp, page_not_found, internal_server_error, forbidden
from .user import user_bp
from .utils import get_supabase

load_dotenv()


def create_app():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static'),
        static_url_path='/static'
    )
    app.secret_key = os.getenv('SECRET_KEY')
    if not app.secret_key:
        raise RuntimeError("SECRET_KEY must be set in environment variables")

    # ====== 新增：Session Cookie 安全配置 ======
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV') == 'production',  # 生产环境启用 HTTPS
    )
    # ==========================================

    # 数据库配置
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # ====== CSRF 保护 ======
    csrf = CSRFProtect()
    csrf.init_app(app)
    # 测试环境禁用 CSRF
    if app.config.get('TESTING'):
        app.config['WTF_CSRF_ENABLED'] = False
    # =============================

    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)

    # 注册错误处理器
    app.register_error_handler(404, page_not_found)
    app.register_error_handler(500, internal_server_error)
    app.register_error_handler(403, forbidden)

    CLUB_NAME = os.getenv('CLUB_NAME', '动漫社')

    @app.context_processor
    def inject_club_name():
        return {'club_name': CLUB_NAME}

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        flash('页面已过期，请重新登录', 'warning')
        session.clear()
        return redirect(url_for('auth.login'))

    # 登录拦截器
    @app.before_request
    def require_login():

        public_routes = [
            'auth.login',
            'auth.register',
            'static',
            'public.splash',
            'auth.forgot_password',
            'auth.forgot_password_bind',
            'auth.reset_password',
            'auth.forgot_bind_send_code',
            'auth.forgot_bind_verify',
            'public.ai_commentary',
            'public.ai_predict'
        ]
        if not session.get('user_id') and request.endpoint not in public_routes and request.endpoint != 'static':
            return redirect(url_for('auth.login'))

    # 版本号
    app.config['APP_VERSION'] = os.getenv('APP_VERSION', 'dev')

    @app.context_processor
    def inject_version():
        return {'app_version': app.config['APP_VERSION']}

    @app.context_processor
    def inject_user():
        role = session.get('user_role')
        is_admin = role in ('owner', 'staff')
        return dict(is_admin=is_admin)

    # ====== 自动注入 CSRF token 到所有模板 ======
    @app.context_processor
    def inject_csrf_token():
        from flask_wtf.csrf import generate_csrf
        return {'csrf_token': generate_csrf}
    # ==================================================

    return app
