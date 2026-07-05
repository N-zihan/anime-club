import base64
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


load_dotenv()

app = Flask(__name__)
app.secret_key = '20090929nzh'

# 在文件顶部，和其他 os.getenv 放在一起
GROUP_VERIFICATION_CODE = os.getenv('GROUP_VERIFICATION_CODE')

# 数据库配置
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("警告: 未设置 DATABASE_URL 环境变量，将使用 SQLite 数据库。")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 图片上传配置（照片墙）
UPLOAD_FOLDER = 'static/upload_photos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


db = SQLAlchemy(app)


# ---------- 数据模型 ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    qq = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    registered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    avatar = db.Column(db.LargeBinary, nullable=True)
    avatar_mime = db.Column(db.String(50), nullable=True)
    is_staff = db.Column(db.Boolean, default=False)
    is_owner = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=False, default='匿名')
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', backref='messages')


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)


class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=False, default='匿名')
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    message = db.relationship('Message', backref=db.backref('replies', lazy='dynamic', order_by='Reply.timestamp'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', backref='replies')


class AnimeResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    link = db.Column(db.String(500), nullable=False)
    extract_code = db.Column(db.String(50))
    upload_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    uploader = db.Column(db.String(50))
    status = db.Column(db.String(20), default='pending')


with app.app_context():
    db.create_all()


# ---------- 后台认证装饰器 ----------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('is_guest'):
            flash('游客不能访问后台', 'warning')
            return redirect(url_for('index'))
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)

    return decorated_function


# ---------- 前台路由 ----------
@app.route('/')
def splash():
    return render_template('splash.html')


@app.route('/home')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    users = User.query.all()
    staff = User.query.filter_by(is_staff=True).all()
    owner = User.query.filter_by(is_owner=True).first()  # 取站长
    return render_template('about.html', users=users, staff=staff, owner=owner)


@app.route('/activities')
def activities():
    activities = Activity.query.order_by(Activity.date.asc()).all()
    return render_template('activities.html', activities=activities)


@app.route('/gallery')
def gallery():
    static_folder = app.static_folder or ''
    image_folder = os.path.join(static_folder, 'history_photos')
    os.makedirs(image_folder, exist_ok=True)
    image_files = [f for f in os.listdir(image_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
    image_urls = [url_for('static', filename=f'history_photos/{img}') for img in image_files]
    return render_template('gallery.html', image_urls=image_urls)


# ---------- 用户认证 ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        qq = request.form.get('qq')
        group = request.form.get('group')
        password = request.form.get('password')
        if group != GROUP_VERIFICATION_CODE:
            flash('验证码错误，请确认你是社团成员', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('用户名已被注册', 'danger')
            return redirect(url_for('register'))
        if not qq.isdigit() or not (5 <= len(qq) <= 12):
            flash('QQ号必须是5-12位数字', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(qq=qq).first():
            flash('该QQ号已注册过', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=username, qq=qq)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('注册成功！请登录', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
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
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'danger')
    return render_template('login.html')


@app.route('/guest_login')
def guest_login():
    guest_id = -abs(hash(str(uuid.uuid4())) % 1000000) - 1
    session['user_id'] = guest_id
    session['username'] = f'游客_{str(uuid.uuid4())[:8]}'
    session['is_guest'] = True
    flash('您已以游客身份登录，部分功能受限（不能留言、推荐、下载番剧等）', 'info')
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('login'))


@app.route('/delete_account', methods=['POST'])
def delete_account():
    if not session.get('user_id') or session.get('is_guest'):
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if user:
        db.session.delete(user)
        db.session.commit()
    session.clear()
    flash('账号已注销', 'info')
    return redirect(url_for('register'))


# ---------- 留言板 ----------
@app.route('/board', methods=['GET', 'POST'])
def board():
    if request.method == 'POST':
        if session.get('is_guest'):
            flash('游客不能发表留言', 'warning')
            return redirect(url_for('board'))
        nickname = session.get('username', '匿名')
        content = request.form.get('content')
        if content:
            msg = Message(
                nickname=nickname,
                content=content,
                user_id=session.get('user_id')  # 新增
            )
            db.session.add(msg)
            db.session.commit()
        return redirect(url_for('board'))

    messages = db.session.query(Message).options(joinedload(Message.user)).order_by(Message.timestamp.desc()).all()
    for msg in messages:
        msg.timestamp = msg.timestamp + timedelta(hours=8)
    return render_template('board.html', messages=messages)


@app.route('/reply/<int:message_id>', methods=['POST'])
def add_reply(message_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if session.get('is_guest'):
        flash('游客不能回复留言', 'warning')
        return redirect(url_for('board'))
    nickname = session.get('username', '匿名')
    content = request.form.get('content')
    if content:
        reply = Reply(
            nickname=nickname,
            content=content,
            message_id=message_id,
            user_id=session.get('user_id')  # 新增
        )
        db.session.add(reply)
        db.session.commit()
    return redirect(url_for('board'))


# ---------- 番剧资源 ----------
@app.route('/anime_resources')
def anime_resources():
    resources = AnimeResource.query.filter_by(status='approved').order_by(AnimeResource.upload_time.desc()).all()
    return render_template('anime_resources.html', resources=resources)


@app.route('/submit_anime', methods=['GET', 'POST'])
def submit_anime():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if session.get('is_guest'):
        flash('游客不能推荐番剧', 'warning')
        return redirect(url_for('anime_resources'))
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        link = request.form.get('link')
        extract_code = request.form.get('extract_code')
        if not title or not link:
            flash('标题和链接不能为空', 'danger')
            return redirect(url_for('submit_anime'))
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
        return redirect(url_for('anime_resources'))
    return render_template('submit_anime.html')


# ---------- 社团成员 ----------
@app.route('/members')
def members():
    # 获取所有用户，按注册时间倒序（最新注册在前）
    users = User.query.order_by(User.registered_at.desc()).all()
    return render_template('members.html', users=users)


# ---------- 个人设置 ----------
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    # 检查用户是否已登录
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('login'))

    # 获取当前用户对象
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        action = request.form.get('action')

        # ---------- 1. 修改头像 ----------
        if action == 'change_avatar':
            if 'avatar' in request.files:
                file = request.files['avatar']
                if file and allowed_file(file.filename):
                    # 限制文件大小（2MB）
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
            return redirect(url_for('profile'))

        # ---------- 2. 修改用户名 ----------
        elif action == 'change_username':
            new_username = request.form.get('new_username', '').strip()
            if not new_username:
                flash('用户名不能为空', 'danger')
            elif len(new_username) < 2 or len(new_username) > 20:
                flash('用户名长度应在2-20个字符之间', 'danger')
            else:
                # 检查是否与其他用户重复（排除自己）
                existing = User.query.filter(User.username == new_username, User.id != user.id).first()
                if existing:
                    flash('该用户名已被占用', 'danger')
                else:
                    old_username = user.username
                    user.username = new_username
                    db.session.commit()
                    session['username'] = new_username  # 更新 session
                    flash(f'用户名已从 "{old_username}" 更新为 "{new_username}"', 'success')
            return redirect(url_for('profile'))

        # ---------- 3. 修改密码 ----------
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
            return redirect(url_for('profile'))

    # GET 请求：显示个人设置页面
    return render_template('profile.html', user=user)


# ---------- 后台管理 ----------
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == os.getenv('ADMIN_PASSWORD', 'your_default_password'):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('密码错误', 'danger')
    return render_template('admin_login.html')


@app.route('/admin/activities')
@admin_required
def admin_activities():
    activities = Activity.query.order_by(Activity.date.desc()).all()
    return render_template('admin_activities.html', activities=activities)


@app.route('/admin/activities/add', methods=['GET', 'POST'])
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
        return redirect(url_for('admin_activities'))
    return render_template('admin_activity_form.html', activity=None)


@app.route('/admin/activities/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_activity_edit(id):
    activity = Activity.query.get_or_404(id)
    if request.method == 'POST':
        activity.title = request.form['title']
        activity.date = request.form['date']
        activity.content = request.form['content']
        db.session.commit()
        flash('活动已更新', 'success')
        return redirect(url_for('admin_activities'))
    return render_template('admin_activity_form.html', activity=activity)


@app.route('/admin/activities/delete/<int:id>')
@admin_required
def admin_activity_delete(id):
    activity = Activity.query.get_or_404(id)
    db.session.delete(activity)
    db.session.commit()
    flash('活动已删除', 'success')
    return redirect(url_for('admin_activities'))


@app.route('/admin/gallery')
@admin_required
def admin_gallery():
    image_folder = os.path.join(app.static_folder, 'history_photos')
    os.makedirs(image_folder, exist_ok=True)
    images = [f for f in os.listdir(image_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
    return render_template('admin_gallery.html', images=images)


@app.route('/admin/gallery/upload', methods=['POST'])
@admin_required
def admin_gallery_upload():
    if 'file' not in request.files:
        flash('没有文件', 'danger')
        return redirect(url_for('admin_gallery'))
    file = request.files['file']
    if file.filename == '':
        flash('未选择文件', 'danger')
        return redirect(url_for('admin_gallery'))
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        base, ext = os.path.splitext(filename)
        counter = 1
        save_path = os.path.join(app.static_folder, 'history_photos', filename)
        while os.path.exists(save_path):
            filename = f"{base}_{counter}{ext}"
            save_path = os.path.join(app.static_folder, 'history_photos', filename)
            counter += 1
        file.save(save_path)
        flash(f'图片 {filename} 上传成功', 'success')
    else:
        flash('不支持的文件类型', 'danger')
    return redirect(url_for('admin_gallery'))


@app.route('/admin/gallery/delete/<filename>')
@admin_required
def admin_gallery_delete(filename):
    file_path = os.path.join(app.static_folder, 'history_photos', filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        flash(f'图片 {filename} 已删除', 'success')
    else:
        flash('文件不存在', 'danger')
    return redirect(url_for('admin_gallery'))


@app.route('/admin/anime_resources')
@admin_required
def admin_anime_resources():
    pending = AnimeResource.query.filter_by(status='pending').order_by(AnimeResource.upload_time.desc()).all()
    approved = AnimeResource.query.filter_by(status='approved').order_by(AnimeResource.upload_time.desc()).all()
    return render_template('admin_anime_resources.html', pending_resources=pending, approved_resources=approved)


@app.route('/admin/anime_resources/approve/<int:id>')
@admin_required
def approve_anime_resource(id):
    resource = AnimeResource.query.get_or_404(id)
    resource.status = 'approved'
    db.session.commit()
    flash('已通过审核', 'success')
    return redirect(url_for('admin_anime_resources'))


@app.route('/admin/anime_resources/reject/<int:id>')
@admin_required
def reject_anime_resource(id):
    resource = AnimeResource.query.get_or_404(id)
    db.session.delete(resource)
    db.session.commit()
    flash('已拒绝并删除', 'warning')
    return redirect(url_for('admin_anime_resources'))


@app.route('/admin/anime_resources/delete/<int:id>')
@admin_required
def admin_anime_resources_delete(id):
    resource = AnimeResource.query.get_or_404(id)
    db.session.delete(resource)
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('admin_anime_resources'))


@app.route('/admin/anime_resources/add', methods=['GET', 'POST'])
@admin_required
def admin_anime_resources_add():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        link = request.form.get('link')
        extract_code = request.form.get('extract_code')
        if not title or not link:
            flash('标题和链接不能为空', 'danger')
            return redirect(url_for('admin_anime_resources_add'))
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
        return redirect(url_for('admin_anime_resources'))
    return render_template('admin_anime_resources_add.html')


@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.registered_at.desc()).all()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/delete/<int:user_id>')
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session.get('user_id'):
        flash('不能删除自己', 'danger')
        return redirect(url_for('admin_users'))
    db.session.delete(user)
    db.session.commit()
    flash('用户已删除', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/toggle_staff/<int:user_id>')
@admin_required
def admin_toggle_staff(user_id):
    user = User.query.get_or_404(user_id)
    user.is_staff = not user.is_staff  # 取反
    db.session.commit()
    flash(f'用户 {user.username} 的运营状态已更新', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/toggle_owner/<int:user_id>')
@admin_required
def admin_toggle_owner(user_id):
    user = User.query.get_or_404(user_id)
    # 如果当前用户不是站长，则先将所有用户置为非站长（保证唯一性）
    if not user.is_owner:
        User.query.update({User.is_owner: False})
        db.session.commit()
    # 切换当前用户的站长状态
    user.is_owner = not user.is_owner
    db.session.commit()
    flash(f'用户 {user.username} 的站长状态已更新', 'success')
    return redirect(url_for('admin_users'))


@app.route('/avatar/<int:user_id>')
def get_avatar(user_id):
    user = User.query.get_or_404(user_id)
    if user.avatar and user.avatar_mime:
        response = Response(user.avatar, mimetype=user.avatar_mime)
    else:
        default = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        response = Response(default, mimetype='image/png')

    # 设置缓存头（放在这里）
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


# ---------- 登录拦截器（未登录用户跳转） ----------
@app.before_request
def require_login():
    public_routes = ['login', 'register', 'static', 'guest_login', 'splash']
    # 允许所有用户（包括游客）访问页面
    if not session.get('user_id') and request.endpoint not in public_routes:
        return redirect(url_for('login'))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
