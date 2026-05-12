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
        nickname = request.form.get('nickname', '匿名')
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
            flash('验证码错误，请确认你是社团成员')
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
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('已退出登录', 'info')
    return redirect(url_for('login'))

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

@app.before_request
def require_login():
    # 公开路由列表（不需要登录就能访问）
    public_routes = ['login', 'register', 'static']
    # 如果用户未登录，且当前请求的端点不在公开列表中，则重定向到登录页
    if not session.get('user_id') and request.endpoint not in public_routes:
        return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)