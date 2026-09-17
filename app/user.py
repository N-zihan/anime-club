"""
动漫社官网 · 用户中心模块
====================================

本模块处理与个人账号相关的功能：

1. 个人设置 (/profile) —— 支持：
   - 更换头像（支持 jpg/png/gif，限制 2MB）
   - 修改用户名（需唯一性校验）
   - 修改密码（需验证原密码）

2. 个人主页 (/user?name=xxx) —— 公开展示用户信息：
   - 用户头像（用边框颜色区分身份：站长金色，运营深色）
   - 最近留言（最多10条）
   - 已通过审核的番剧推荐

3. 头像获取 (/avatar/<user_id>) —— 返回用户头像图片：
   - 从数据库读取二进制数据
   - 若未设置则返回默认透明图
   - 设置浏览器缓存（1天）
"""

import base64
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, Response, jsonify
from sqlalchemy import func

from .config import AVATAR_MAX_SIZE
from .models import db, User, Message, AnimeResource, Notification
from .utils import allowed_file, compress_image, get_or_404

user_bp = Blueprint('user', __name__)

# ---------- 发邮件函数（复用 auth 的） ----------
from .auth import send_verification_email, send_welcome_email


@user_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])

    if request.method == 'POST':
        action = request.form.get('action')

        # ---------- 更换头像 ----------
        if action == 'change_avatar':
            if 'avatar' in request.files:
                file = request.files['avatar']
                if file and allowed_file(file.filename):
                    if request.content_length and request.content_length > AVATAR_MAX_SIZE:
                        flash('头像文件不能超过2MB', 'danger')
                    else:
                        raw_data = file.read()
                        compressed = compress_image(raw_data, max_size=(200, 200), quality=80)
                        user.avatar = compressed
                        user.avatar_mime = 'image/jpeg'
                        db.session.commit()
                        flash('头像更新成功', 'success')
                else:
                    flash('不支持的文件类型（支持 png, jpg, jpeg, gif）', 'danger')
            return redirect(url_for('user.profile'))

        # ---------- 修改用户名 ----------
        if action == 'change_username':
            new_username = request.form.get('new_username', '').strip()
            if not new_username:
                flash('用户名不能为空', 'danger')
            elif len(new_username) < 2 or len(new_username) > 20:
                flash('用户名长度应在2-20个字符之间', 'danger')
            else:
                existing = User.query.filter(User.username == new_username, User.id != user.id).first()
                if existing:
                    flash('该用户名已被占用', 'danger')
                else:
                    old_username = user.username
                    user.username = new_username
                    db.session.commit()
                    session['username'] = new_username
                    flash(f'用户名已从 "{old_username}" 更新为 "{new_username}"', 'success')
            return redirect(url_for('user.profile'))

        # ---------- 绑定邮箱：验证验证码 ----------
        # 绑定邮箱：验证验证码
        if action == 'verify_email_code':
            code = request.form.get('code')
            stored_code = session.get('profile_email_code')
            pending_email = session.get('profile_pending_email')

            if not pending_email:
                return jsonify({'error': '请先发送验证码'}), 400
            if not stored_code or stored_code != code:
                return jsonify({'error': '验证码错误'}), 400

            expires = session.get('profile_email_expires')
            if expires and datetime.fromisoformat(expires) < datetime.now():
                return jsonify({'error': '验证码已过期，请重新获取'}), 400

            user.email = pending_email
            db.session.commit()
            session.pop('profile_email_code', None)
            session.pop('profile_pending_email', None)
            session.pop('profile_email_expires', None)
            session.pop('show_bind_prompt', None)

            # 发送欢迎邮件（失败不影响绑定结果）
            try:
                send_welcome_email(pending_email, user.username)
            except Exception as e:
                print(f'欢迎邮件发送失败: {e}')

            return jsonify({'success': True, 'message': '邮箱绑定成功', 'email': pending_email})

    return render_template('profile.html', user=user)


@user_bp.route('/change_password', methods=['GET', 'POST'])
def change_password():
    """独立的修改密码页面"""
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        old = request.form.get('old_password')
        new = request.form.get('new_password')
        confirm = request.form.get('confirm_password')

        if not user.check_password(old):
            flash('原密码错误', 'danger')
            return redirect(url_for('user.change_password'))
        elif new != confirm:
            flash('两次输入的新密码不一致', 'danger')
            return redirect(url_for('user.change_password'))
        elif len(new) < 6:
            flash('新密码至少6位', 'danger')
            return redirect(url_for('user.change_password'))
        elif new == old:
            flash('新密码不能与原密码相同', 'danger')
            return redirect(url_for('user.change_password'))
        else:
            user.set_password(new)
            db.session.commit()
            flash('密码修改成功', 'success')
            return redirect(url_for('user.profile'))

    return render_template('change_password.html', user=user)


@user_bp.route('/bind_email', methods=['GET', 'POST'])
def bind_email():
    """独立的绑定/更换邮箱页面"""
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        action = request.form.get('action')

        # ---------- 发送验证码 ----------
        if action == 'send_email_code':
            email = request.form.get('email')
            if not email:
                return jsonify({'error': '邮箱不能为空'}), 400
            if User.query.filter(User.email == email, User.id != user.id).first():
                return jsonify({'error': '该邮箱已被其他用户绑定'}), 400

            code = ''.join(secrets.choice('0123456789') for _ in range(6))
            session['profile_email_code'] = code
            session['profile_pending_email'] = email
            session['profile_email_expires'] = (datetime.now() + timedelta(minutes=10)).isoformat()

            if send_verification_email(email, code):
                return jsonify({'success': True, 'message': '验证码已发送'})
            return jsonify({'error': '邮件发送失败，请检查邮箱地址'}), 500

        # ---------- 验证并绑定 ----------
        if action == 'verify_email_code':
            code = request.form.get('code')
            stored_code = session.get('profile_email_code')
            pending_email = session.get('profile_pending_email')

            if not pending_email:
                return jsonify({'error': '请先发送验证码'}), 400
            if not stored_code or stored_code != code:
                return jsonify({'error': '验证码错误'}), 400

            expires = session.get('profile_email_expires')
            if expires and datetime.fromisoformat(expires) < datetime.now():
                return jsonify({'error': '验证码已过期，请重新获取'}), 400

            user.email = pending_email
            db.session.commit()
            session.pop('profile_email_code', None)
            session.pop('profile_pending_email', None)
            session.pop('profile_email_expires', None)
            session.pop('show_bind_prompt', None)

            try:
                send_welcome_email(pending_email, user.username)
            except Exception as e:
                print(f'欢迎邮件发送失败: {e}')

            return jsonify({'success': True, 'message': '邮箱绑定成功', 'email': pending_email})

    return render_template('bind_email.html', user=user)


# ---------- 个人主页 ----------
@user_bp.route('/user')
def user_profile():
    username = request.args.get('name')
    if not username:
        abort(404)
    user = User.query.filter(func.lower(User.username) == func.lower(username.strip())).first()
    if not user:
        abort(404)
    messages = Message.query.filter_by(user_id=user.id).order_by(Message.timestamp.desc()).limit(10).all()
    for msg in messages:
        msg.timestamp = msg.timestamp + timedelta(hours=8)
    anime = AnimeResource.query.filter_by(user_id=user.id, status='approved').order_by(
        AnimeResource.upload_time.desc()).all()
    return render_template('user_profile.html', user=user, messages=messages, anime=anime)


# ---------- 头像 ----------
@user_bp.route('/avatar/<int:user_id>')
def get_avatar(user_id):
    user = get_or_404(User, user_id)
    if user.avatar and user.avatar_mime:
        response = Response(user.avatar, mimetype=user.avatar_mime)
    else:
        default = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        response = Response(default, mimetype='image/png')
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@user_bp.route('/dismiss_bind_prompt')
def dismiss_bind_prompt():
    session.pop('show_bind_prompt', None)
    return redirect(url_for('public.index'))


@user_bp.route('/notifications')
def notifications():
    """通知列表页"""
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))

    items = Notification.query.filter_by(
        user_id=session['user_id']
    ).order_by(Notification.created_at.desc()).all()

    # 时间转东八区
    for n in items:
        n.created_at = n.created_at + timedelta(hours=8)

    return render_template('notifications.html', notifications=items)


@user_bp.route('/notifications/read/<int:nid>')
def notification_read(nid):
    """标记单条已读并跳转"""
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    n = db.session.get(Notification, nid)
    if n and n.user_id == session['user_id']:
        n.is_read = True
        db.session.commit()
        if n.link:
            return redirect(n.link)
    return redirect(url_for('user.notifications'))


@user_bp.route('/notifications/read_all')
def notification_read_all():
    """全部标记已读"""
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    Notification.query.filter_by(
        user_id=session['user_id'],
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    flash('已全部标记为已读', 'success')
    return redirect(url_for('user.notifications'))


@user_bp.route('/api/notifications/count')
def notification_count():
    """返回未读数（给导航栏铃铛用）"""
    if not session.get('user_id'):
        return jsonify({'count': 0})
    count = Notification.query.filter_by(
        user_id=session['user_id'],
        is_read=False
    ).count()
    return jsonify({'count': count})
