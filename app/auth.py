"""
南平一中动漫社官网 · 用户认证模块
====================================

本模块处理社员账号的注册、登录、登出和注销功能。

核心设计：
- 注册时要求填写社团 QQ 群号作为验证码，防止校外人员注册
- 用户名支持中文、字母、数字、下划线（2-20位）
- QQ 号需为 5-12 位纯数字
- 密码使用 werkzeug 进行哈希存储

登录成功后自动判断用户角色：
- is_owner=True → 站长身份（session.user_role = 'owner'）
- is_staff=True → 运营身份（session.user_role = 'staff'）
- 普通社员 → session.user_role = 'member'

这些角色信息用于导航栏显示"管理"入口以及权限控制。
"""

import os
import re

from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from .models import db, User

auth_bp = Blueprint('auth', __name__)

GROUP_VERIFICATION_CODE = os.getenv('GROUP_VERIFICATION_CODE')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        qq = request.form.get('qq')
        group = request.form.get('group')
        password = request.form.get('password')

        username_pattern = r'^[\u4e00-\u9fa5A-Za-z0-9_]{2,20}$'
        if not re.match(username_pattern, username):
            flash('用户名只允许中文、字母、数字、下划线，长度2-20个字符', 'danger')
            return redirect(url_for('auth.register'))

        if group != GROUP_VERIFICATION_CODE:
            flash('验证码错误，请确认你是社团成员', 'danger')
            return redirect(url_for('auth.register'))
        if User.query.filter_by(username=username).first():
            flash('用户名已被注册', 'danger')
            return redirect(url_for('auth.register'))
        if not qq.isdigit() or not (5 <= len(qq) <= 12):
            flash('QQ号必须是5-12位数字', 'danger')
            return redirect(url_for('auth.register'))
        if User.query.filter_by(qq=qq).first():
            flash('该QQ号已注册过', 'danger')
            return redirect(url_for('auth.register'))
        new_user = User(username=username, qq=qq)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('注册成功！请登录', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    username = ''  # 默认空值，用于GET请求
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username

            if user.is_owner:
                session['user_role'] = 'owner'
            elif user.is_staff:
                session['user_role'] = 'staff'
            else:
                session['user_role'] = 'member'

            flash('登录成功', 'success')
            return redirect(url_for('public.index'))
        else:
            flash('用户名或密码错误', 'danger')
            # 关键修改：登录失败时把用户名传回模板，不清空
            return render_template('login.html', username=username)
    return render_template('login.html', username=username)


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/delete_account', methods=['POST'])
def delete_account():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    user = db.session.get(User, session['user_id'])
    if user:
        db.session.delete(user)
        db.session.commit()
    session.clear()
    flash('账号已注销', 'info')
    return redirect(url_for('auth.register'))
