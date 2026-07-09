from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from .models import db, User
import re
import os

auth_bp = Blueprint('auth', __name__)

GROUP_VERIFICATION_CODE = os.getenv('GROUP_VERIFICATION_CODE')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        qq = request.form.get('qq')
        group = request.form.get('group')
        password = request.form.get('password')

        if not re.match(r'^[A-Za-z0-9_]{2,20}$', username):
            flash('用户名只允许字母、数字、下划线，长度2-20个字符', 'danger')
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
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session.pop('is_guest', None)
            flash('登录成功', 'success')
            return redirect(url_for('public.index'))
        else:
            flash('用户名或密码错误', 'danger')
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/delete_account', methods=['POST'])
def delete_account():
    if not session.get('user_id') or session.get('is_guest'):
        return redirect(url_for('auth.login'))
    user = User.query.get(session['user_id'])
    if user:
        db.session.delete(user)
        db.session.commit()
    session.clear()
    flash('账号已注销', 'info')
    return redirect(url_for('auth.register'))