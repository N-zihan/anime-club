"""
南平一中动漫社官网 · 用户中心模块
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

注意：个人主页使用查询参数传递用户名，而非 URL 路径，
这是为了解决中文用户名导致的编码问题。
"""

import base64
from datetime import timedelta

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, Response
from sqlalchemy import func

from .models import db, User, Message, AnimeResource
from .utils import allowed_file

user_bp = Blueprint('user', __name__)


@user_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'change_avatar':
            if 'avatar' in request.files:
                file = request.files['avatar']
                if file and allowed_file(file.filename):
                    if request.content_length and request.content_length > 2 * 1024 * 1024:
                        flash('头像文件不能超过2MB', 'danger')
                    else:
                        avatar_data = file.read()
                        avatar_mime = file.content_type or 'image/png'
                        user.avatar = avatar_data
                        user.avatar_mime = avatar_mime
                        db.session.commit()
                        flash('头像更新成功', 'success')
                else:
                    flash('不支持的文件类型（支持 png, jpg, jpeg, gif）', 'danger')
            return redirect(url_for('user.profile'))

        elif action == 'change_username':
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

        elif action == 'change_password':
            old = request.form.get('old_password')
            new = request.form.get('new_password')
            confirm = request.form.get('confirm_password')
            if not user.check_password(old):
                flash('原密码错误', 'danger')
            elif new != confirm:
                flash('两次输入的新密码不一致', 'danger')
            elif len(new) < 6:
                flash('新密码至少6位', 'danger')
            else:
                user.set_password(new)
                db.session.commit()
                flash('密码修改成功', 'success')
            return redirect(url_for('user.profile'))

    return render_template('profile.html', user=user)


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
    # 通过 user_id 查询推荐记录
    anime = AnimeResource.query.filter_by(user_id=user.id, status='approved').order_by(
        AnimeResource.upload_time.desc()).all()
    return render_template('user_profile.html', user=user, messages=messages, anime=anime)


@user_bp.route('/avatar/<int:user_id>')
def get_avatar(user_id):
    user = User.query.get_or_404(user_id)
    if user.avatar and user.avatar_mime:
        response = Response(user.avatar, mimetype=user.avatar_mime)
    else:
        default = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        response = Response(default, mimetype='image/png')
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response
