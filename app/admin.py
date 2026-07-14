import uuid
from datetime import datetime
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from .models import db, User, Activity, Photo, AnimeResource
from .utils import supabase, allowed_file

admin_bp = Blueprint('admin', __name__)


# ---------- 权限装饰器 ----------
def admin_required(f):
    """运营或站长均可访问，直接从 Session 读取角色"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        role = session.get('user_role')
        if role not in ('owner', 'staff'):
            flash('你没有管理权限', 'danger')
            return redirect(url_for('public.index'))
        return f(*args, **kwargs)

    return decorated_function


def owner_required(f):
    """仅站长可访问，直接从 Session 读取角色"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'owner':
            flash('该功能仅站长可用', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)

    return decorated_function


# ---------- 统一入口 ----------
@admin_bp.route('/admin/entry')
def admin_entry():
    role = session.get('user_role')
    if role == 'owner':
        return redirect(url_for('admin.dashboard'))
    elif role == 'staff':
        return redirect(url_for('admin.staff_dashboard'))
    else:
        flash('你没有管理权限', 'danger')
        return redirect(url_for('public.index'))


# ---------- 站长后台 ----------
@admin_bp.route('/admin/dashboard')
@admin_required
def dashboard():
    return render_template('admin_dashboard.html')


# ---------- 运营后台 ----------
@admin_bp.route('/staff/dashboard')
@admin_required
def staff_dashboard():
    return render_template('staff_dashboard.html')


# ---------- 活动管理 ----------
@admin_bp.route('/admin/activities')
@admin_required
def admin_activities():
    activities = Activity.query.order_by(Activity.date.desc()).all()
    return render_template('admin_activities.html', activities=activities)


@admin_bp.route('/admin/activities/add', methods=['GET', 'POST'])
@admin_required
def admin_activity_add():
    if request.method == 'POST':
        title = request.form['title']
        date = request.form['date']
        content = request.form['content']
        new_activity = Activity(title=title, date=date, content=content)
        db.session.add(new_activity)
        db.session.commit()
        flash('活动添加成功', 'success')
        return redirect(url_for('admin.admin_activities'))
    return render_template('admin_activity_form.html', activity=None)


@admin_bp.route('/admin/activities/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_activity_edit(id):
    activity = Activity.query.get_or_404(id)
    if request.method == 'POST':
        activity.title = request.form['title']
        activity.date = request.form['date']
        activity.content = request.form['content']
        db.session.commit()
        flash('活动已更新', 'success')
        return redirect(url_for('admin.admin_activities'))
    return render_template('admin_activity_form.html', activity=activity)


@admin_bp.route('/admin/activities/delete/<int:id>')
@admin_required
def admin_activity_delete(id):
    activity = Activity.query.get_or_404(id)

    # 先删除该活动关联的所有照片（文件 + 数据库记录）
    for photo in activity.photos:
        try:
            supabase.storage.from_('photos').remove([photo.filename])
        except Exception:
            pass  # 云文件删不掉也继续，至少删数据库记录
        db.session.delete(photo)

    db.session.delete(activity)
    db.session.commit()
    flash('活动及其所有照片已删除', 'success')
    return redirect(url_for('admin.admin_activities'))


# ---------- 照片墙管理 ----------
@admin_bp.route('/admin/gallery')
@admin_required
def admin_gallery():
    activities = Activity.query.order_by(Activity.date.desc()).all()
    photos = Photo.query.order_by(Photo.upload_time.desc()).all()
    for photo in photos:
        photo.url = supabase.storage.from_('photos').get_public_url(photo.filename)
    return render_template('admin_gallery.html', activities=activities, photos=photos)


@admin_bp.route('/admin/gallery/upload', methods=['POST'])
def admin_gallery_upload():
    if not session.get('user_id'):
        flash('请先登录再上传照片', 'warning')
        return redirect(url_for('auth.login'))

    if 'file' not in request.files:
        flash('没有文件', 'danger')
        return redirect(url_for('admin.admin_gallery'))
    file = request.files['file']
    if file.filename == '':
        flash('未选择文件', 'danger')
        return redirect(url_for('admin.admin_gallery'))

    activity_id = request.form.get('activity_id')
    if activity_id:
        activity_id = int(activity_id)

    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"

        try:
            supabase.storage.from_('photos').upload(
                filename,
                file.read(),
                file_options={"content-type": file.content_type}
            )
        except Exception as e:
            flash(f'上传失败: {str(e)}', 'danger')
            return redirect(url_for('admin.admin_gallery'))

        photo = Photo(
            filename=filename,
            activity_id=activity_id if activity_id else None,
            uploader=session.get('username', '社员')  # 记录上传者
        )
        db.session.add(photo)
        db.session.commit()
        flash('照片上传成功', 'success')
    else:
        flash('不支持的文件类型', 'danger')
    return redirect(url_for('admin.admin_gallery'))


# ---------- 番剧资源管理 ----------
@admin_bp.route('/admin/anime_resources')
@admin_required
def admin_anime_resources():
    pending = AnimeResource.query.filter_by(status='pending').order_by(AnimeResource.upload_time.desc()).all()
    approved = AnimeResource.query.filter_by(status='approved').order_by(AnimeResource.upload_time.desc()).all()
    return render_template('admin_anime_resources.html', pending_resources=pending, approved_resources=approved)


@admin_bp.route('/admin/anime_resources/approve/<int:id>')
@admin_required
def approve_anime_resource(id):
    resource = AnimeResource.query.get_or_404(id)
    resource.status = 'approved'
    db.session.commit()
    flash('已通过审核', 'success')
    return redirect(url_for('admin.admin_anime_resources'))


@admin_bp.route('/admin/anime_resources/reject/<int:id>')
@admin_required
def reject_anime_resource(id):
    resource = AnimeResource.query.get_or_404(id)
    db.session.delete(resource)
    db.session.commit()
    flash('已拒绝并删除', 'warning')
    return redirect(url_for('admin.admin_anime_resources'))


@admin_bp.route('/admin/anime_resources/delete/<int:id>')
@admin_required
def admin_anime_resources_delete(id):
    resource = AnimeResource.query.get_or_404(id)
    db.session.delete(resource)
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('admin.admin_anime_resources'))


@admin_bp.route('/admin/anime_resources/add', methods=['GET', 'POST'])
@admin_required
def admin_anime_resources_add():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        link = request.form.get('link')
        extract_code = request.form.get('extract_code')
        if not title or not link:
            flash('标题和链接不能为空', 'danger')
            return redirect(url_for('admin.admin_anime_resources_add'))
        resource = AnimeResource(
            title=title,
            description=description,
            link=link,
            extract_code=extract_code,
            uploader=session.get('username', 'admin'),
            status='approved'
        )
        db.session.add(resource)
        db.session.commit()
        flash('资源添加成功', 'success')
        return redirect(url_for('admin.admin_anime_resources'))
    return render_template('admin_anime_resources_add.html')


# ---------- 用户管理 ----------
@admin_bp.route('/admin/users')
@admin_required
@owner_required
def admin_users():
    users = User.query.order_by(User.registered_at.desc()).all()
    return render_template('admin_users.html', users=users)


@admin_bp.route('/admin/users/delete/<int:user_id>')
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session.get('user_id'):
        flash('不能删除自己', 'danger')
        return redirect(url_for('admin.admin_users'))
    db.session.delete(user)
    db.session.commit()
    flash('用户已删除', 'success')
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/toggle_staff/<int:user_id>')
@admin_required
def admin_toggle_staff(user_id):
    user = User.query.get_or_404(user_id)
    user.is_staff = not user.is_staff
    db.session.commit()
    flash(f'用户 {user.username} 的运营状态已更新', 'success')
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/toggle_owner/<int:user_id>')
@admin_required
def admin_toggle_owner(user_id):
    user = User.query.get_or_404(user_id)
    if not user.is_owner:
        User.query.update({User.is_owner: False})
        db.session.commit()
    user.is_owner = not user.is_owner
    db.session.commit()
    flash(f'用户 {user.username} 的站长状态已更新', 'success')
    return redirect(url_for('admin.admin_users'))
