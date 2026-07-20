"""
南平一中动漫社官网 · 公共页面模块
====================================

本模块处理所有对客端可见的页面（无需登录或部分需要登录）：

1. 启动页 (/) —— 带有 Canvas 波浪粒子动画的品牌页面
2. 首页 (/home) —— 卡片导航式入口
3. 社团介绍 (/about) —— 展示站长、运营团队和技术栈
4. 活动列表 (/activities) —— 按日期排序的所有活动
5. 照片墙 (/gallery) —— 按活动分类展示历史图片
6. 留言板 (/board) —— 社员自由交流，支持嵌套回复
7. 番剧资源 (/anime_resources) —— 展示已审核通过的资源
8. 番剧推荐 (/submit_anime) —— 社员提交资源，待审核
9. 社员名单 (/members) —— 展示所有注册社员

此外，本模块还注册了全局错误处理器：
400、403、404、405、413、500 均有对应的自定义页面。
"""

from datetime import timedelta

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy.orm import joinedload

from .models import db, User, Activity, Photo, Message, Reply, AnimeResource
from .utils import supabase

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def splash():
    return render_template('splash.html')


@public_bp.route('/home')
def index():
    return render_template('index.html')


@public_bp.route('/about')
def about():
    users = User.query.all()
    staff = User.query.filter_by(is_staff=True).all()
    owner = User.query.filter_by(is_owner=True).first()
    return render_template('about.html', users=users, staff=staff, owner=owner)


@public_bp.route('/activities')
def activities():
    activities = Activity.query.order_by(Activity.date.asc()).all()
    return render_template('activities.html', activities=activities)


@public_bp.route('/gallery')
def gallery():
    activities = Activity.query.options(joinedload(Activity.photos)).order_by(Activity.date.desc()).all()
    uncategorized_photos = Photo.query.filter_by(activity_id=None).all()

    for photo in uncategorized_photos:
        photo.url = supabase.storage.from_('photos').get_public_url(photo.filename)
    for activity in activities:
        for photo in activity.photos:
            photo.url = supabase.storage.from_('photos').get_public_url(photo.filename)

    return render_template('gallery.html', activities=activities, uncategorized_photos=uncategorized_photos)


@public_bp.route('/board', methods=['GET', 'POST'])
def board():
    if request.method == 'POST':
        if session.get('is_guest'):
            flash('游客不能发表留言', 'warning')
            return redirect(url_for('public.board'))
        nickname = session.get('username', '匿名')
        content = request.form.get('content')
        if content:
            msg = Message(
                nickname=nickname,
                content=content,
                user_id=session.get('user_id')
            )
            db.session.add(msg)
            db.session.commit()
        return redirect(url_for('public.board'))

    # 获取所有留言（预加载用户）
    messages = db.session.query(Message).options(
        joinedload(Message.user)
    ).order_by(Message.timestamp.desc()).all()

    # 获取所有回复（预加载用户和父回复用户）
    all_replies = Reply.query.options(
        joinedload(Reply.user),
        joinedload(Reply.parent_reply).joinedload(Reply.user)
    ).order_by(Reply.timestamp.asc()).all()

    # 回复时间加8小时（东八区）
    for reply in all_replies:
        reply.timestamp = reply.timestamp + timedelta(hours=8)

    # 为每条留言筛选出其对应的回复列表
    reply_dict_by_msg = {}
    for reply in all_replies:
        if reply.message_id not in reply_dict_by_msg:
            reply_dict_by_msg[reply.message_id] = []
        reply_dict_by_msg[reply.message_id].append(reply)

    for msg in messages:
        msg.timestamp = msg.timestamp + timedelta(hours=8)
        msg._replies = reply_dict_by_msg.get(msg.id, [])

    return render_template('board.html', messages=messages)


@public_bp.route('/reply/<int:message_id>', methods=['POST'])
def add_reply(message_id):
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    if session.get('is_guest'):
        flash('游客不能回复留言', 'warning')
        return redirect(url_for('public.board'))

    nickname = session.get('username', '匿名')
    content = request.form.get('content')
    parent_reply_id = request.form.get('parent_reply_id')

    if content:
        reply = Reply(
            nickname=nickname,
            content=content,
            message_id=message_id,
            user_id=session.get('user_id'),
            parent_reply_id=int(parent_reply_id) if parent_reply_id else None
        )
        db.session.add(reply)
        db.session.commit()
    return redirect(url_for('public.board'))


@public_bp.route('/anime_resources')
def anime_resources():
    resources = AnimeResource.query.filter_by(status='approved').order_by(AnimeResource.upload_time.desc()).all()
    return render_template('anime_resources.html', resources=resources)


@public_bp.route('/submit_anime', methods=['GET', 'POST'])
def submit_anime():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    if session.get('is_guest'):
        flash('游客不能推荐番剧', 'warning')
        return redirect(url_for('public.anime_resources'))
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        link = request.form.get('link')
        extract_code = request.form.get('extract_code')
        if not title or not link:
            flash('标题和链接不能为空', 'danger')
            return redirect(url_for('public.submit_anime'))
        new_resource = AnimeResource(
            title=title,
            description=description,
            link=link,
            extract_code=extract_code,
            user_id=session.get('user_id'),  # 只存 user_id
            status='pending'
        )
        db.session.add(new_resource)
        db.session.commit()
        flash('提交成功，等待管理员审核', 'success')
        return redirect(url_for('public.anime_resources'))
    return render_template('submit_anime.html')


@public_bp.route('/members')
def members():
    users = User.query.order_by(User.registered_at.desc()).all()
    return render_template('members.html', users=users)


# 错误处理器
def page_not_found(e):
    return render_template('404.html'), 404


def internal_server_error(e):
    return render_template('500.html'), 500


def forbidden(e):
    return render_template('403.html'), 403


@public_bp.app_errorhandler(405)
def method_not_allowed(e):
    return render_template('405.html'), 405


@public_bp.app_errorhandler(400)
def bad_request(e):
    return render_template('400.html'), 400


@public_bp.app_errorhandler(413)
def request_entity_too_large(e):
    return render_template('413.html'), 413
