from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy.orm import joinedload
from datetime import timedelta
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

    messages = db.session.query(Message).options(joinedload(Message.user)).order_by(Message.timestamp.desc()).all()
    for msg in messages:
        msg.timestamp = msg.timestamp + timedelta(hours=8)
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
    if content:
        reply = Reply(
            nickname=nickname,
            content=content,
            message_id=message_id,
            user_id=session.get('user_id')
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
            uploader=session.get('username'),
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