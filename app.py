import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = '20090929nzh'

# 数据库配置
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("警告: 未设置 DATABASE_URL 环境变量，将使用 SQLite 数据库。")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

else:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 图片上传配置
UPLOAD_FOLDER = 'static/upload_photos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 番剧资源上传目录
ANIME_UPLOAD_FOLDER = 'static/anime_zips'
ALLOWED_ZIP_EXTENSIONS = {'zip'}
app.config['ANIME_UPLOAD_FOLDER'] = ANIME_UPLOAD_FOLDER

# 确保目录存在
os.makedirs(ANIME_UPLOAD_FOLDER, exist_ok=True)

def allowed_zip(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ZIP_EXTENSIONS

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

# ---------- 数据模型 ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    qq = db.Column(db.String(20), unique=True, nullable=False)   # QQ号唯一
    password_hash = db.Column(db.String(255), nullable=False)
    registered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=False, default='匿名')
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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

class AnimeResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    filename = db.Column(db.String(200), nullable=False)
    upload_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    uploader = db.Column(db.String(50), nullable=True)   # 记录管理员用户名

    def __repr__(self):
        return f'<AnimeResource {self.title}>'

with app.app_context():
    db.create_all()

# ---------- 后台认证 ----------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == os.getenv('ADMIN_PASSWORD', 'your_default_password'):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_activities'))
        else:
            flash('密码错误')
    return render_template('admin_login.html')

# ---------- 公开页面 ----------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

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

# ---------- 留言板（需要登录）----------
@app.route('/board', methods=['GET', 'POST'])
def board():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        nickname = session.get('username', '匿名')   # 自动使用登录用户名
        content = request.form.get('content')
        if content:
            msg = Message(nickname=nickname, content=content)
            db.session.add(msg)
            db.session.commit()
        return redirect(url_for('board'))

    messages = db.session.query(Message).order_by(Message.timestamp.desc()).all()
    for msg in messages:
        msg.timestamp = msg.timestamp + timedelta(hours=8)
    return render_template('board.html', messages=messages)

    messages = db.session.query(Message).order_by(Message.timestamp.desc()).all()
    for msg in messages:
        msg.timestamp = msg.timestamp + timedelta(hours=8)
    return render_template('board.html', messages=messages)

@app.route('/reply/<int:message_id>', methods=['POST'])
def add_reply(message_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    nickname = request.form.get('nickname', '匿名')
    content = request.form.get('content')
    if content:
        reply = Reply(nickname=nickname, content=content, message_id=message_id)
        db.session.add(reply)
        db.session.commit()
    return redirect(url_for('board'))

# ---------- 用户注册与登录 ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        qq = request.form.get('qq')
        group = request.form.get('group')
        password = request.form.get('password')

        # 验证社团验证码 = 动漫社QQ群号 (582651609)
        if group != '582651609':
            flash('群号错误，请确认你是社团成员')
            return redirect(url_for('register'))

        # 用户名唯一性
        if User.query.filter_by(username=username).first():
            flash('用户名已被注册')
            return redirect(url_for('register'))

        # QQ号格式验证
        if not qq.isdigit() or not (5 <= len(qq) <= 12):
            flash('QQ号必须是5-12位数字')
            return redirect(url_for('register'))

        # QQ号唯一性
        if User.query.filter_by(qq=qq).first():
            flash('该QQ号已注册过')
            return redirect(url_for('register'))

        # 创建用户
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
        # 前端验证非空
        if not username or not password:
            flash('请填写用户名和密码', 'danger')
        else:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                session['user_id'] = user.id
                session['username'] = user.username
                flash('登录成功', 'success')
                return redirect(url_for('index'))
            else:
                if not user:
                    flash('用户名不存在，请先注册', 'danger')
                else:
                    flash('密码错误', 'danger')
    return render_template('login.html')

# ---------- 后台管理 ----------
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
        flash('活动添加成功')
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
        flash('活动已更新')
        return redirect(url_for('admin_activities'))
    return render_template('admin_activity_form.html', activity=activity)

@app.route('/admin/activities/delete/<int:id>')
@admin_required
def admin_activity_delete(id):
    activity = Activity.query.get_or_404(id)
    db.session.delete(activity)
    db.session.commit()
    flash('活动已删除')
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
        flash('没有文件')
        return redirect(url_for('admin_gallery'))
    file = request.files['file']
    if file.filename == '':
        flash('未选择文件')
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
        flash(f'图片 {filename} 上传成功')
    else:
        flash('不支持的文件类型')
    return redirect(url_for('admin_gallery'))

@app.route('/admin/gallery/delete/<filename>')
@admin_required
def admin_gallery_delete(filename):
    file_path = os.path.join(app.static_folder, 'history_photos', filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        flash(f'图片 {filename} 已删除')
    else:
        flash('文件不存在')
    return redirect(url_for('admin_gallery'))

@app.route('/admin/anime_resources', methods=['GET', 'POST'])
@admin_required
def admin_anime_resources():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        file = request.files.get('file')
        if not title or not file or not allowed_zip(file.filename):
            flash('请填写标题并上传 zip 文件')
            return redirect(url_for('admin_anime_resources'))
        filename = secure_filename(file.filename)
        # 避免重名
        base, ext = os.path.splitext(filename)
        counter = 1
        save_path = os.path.join(app.config['ANIME_UPLOAD_FOLDER'], filename)
        while os.path.exists(save_path):
            filename = f"{base}_{counter}{ext}"
            save_path = os.path.join(app.config['ANIME_UPLOAD_FOLDER'], filename)
            counter += 1
        file.save(save_path)
        resource = AnimeResource(
            title=title,
            description=description,
            filename=filename,
            uploader=session.get('username', 'admin')
        )
        db.session.add(resource)
        db.session.commit()
        flash('资源上传成功')
        return redirect(url_for('admin_anime_resources'))

    resources = AnimeResource.query.order_by(AnimeResource.upload_time.desc()).all()
    return render_template('admin_anime_resources.html', resources=resources)

@app.route('/admin/anime_resources/delete/<int:id>')
@admin_required
def admin_anime_resources_delete(id):
    resource = AnimeResource.query.get_or_404(id)
    file_path = os.path.join(app.config['ANIME_UPLOAD_FOLDER'], resource.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(resource)
    db.session.commit()
    flash('资源已删除')
    return redirect(url_for('admin_anime_resources'))

@app.before_request
def require_login():
    # 公开路由列表（不需要登录就能访问）
    public_routes = ['login', 'register', 'static']
    # 如果用户未登录，且当前请求的端点不在公开列表中，则重定向到登录页
    if not session.get('user_id') and request.endpoint not in public_routes:
        return redirect(url_for('login'))


# 退出登录（已有，确认正确即可）
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('已退出登录', 'info')
    return redirect(url_for('login'))


# 注销账号（彻底删除用户及其所有关联数据）
@app.route('/delete_account', methods=['POST'])
def delete_account():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('login'))

    # 可选：删除该用户的所有留言和回复（根据需求）
    # 注意：留言有 replies 外键，需先删除 replies 或建立级联删除。
    # 为了简单，我们只删除用户，留言保留但显示“已注销用户”。
    # 如果你想彻底删除用户的所有留言，请取消下面注释（需先处理 replies）。

    # 删除用户
    db.session.delete(user)
    db.session.commit()

    # 清除 session
    session.clear()
    flash('账号已注销，感谢曾经参与', 'info')
    return redirect(url_for('register'))

@app.route('/anime_resources')
def anime_resources():
    resources = AnimeResource.query.order_by(AnimeResource.upload_time.desc()).all()
    return render_template('anime_resources.html', resources=resources)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)