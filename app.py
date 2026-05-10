import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import session, flash
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = '20090929nzh'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# --- 在 app = Flask(__name__) 之后添加配置 ---
# 配置图片上传的保存文件夹 (在 static 目录下)
UPLOAD_FOLDER = 'static/upload_photos'
# 定义允许上传的文件类型白名单
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- 定义 allowed_file 函数 ---
# 这个函数用来检查上传的文件名是否以白名单中的后缀结尾
def allowed_file(filename):
    """检查文件名是否合法 (是否有 . 并且后缀在白名单里)"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

# 留言板模型
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=False, default='匿名')
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Message {self.nickname}>'

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)   # 格式 YYYY-MM-DD
    content = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f'<Activity {self.title}>'

class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=False, default='匿名')  # 新增
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    message = db.relationship('Message', backref=db.backref('replies', lazy='dynamic', order_by='Reply.timestamp'))

# 后台登录验证装饰器
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

# 创建表
with app.app_context():
    db.create_all()

# 路由
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/activities')
def activities():
    activities = Activity.query.order_by(Activity.date.asc()).all()   # 按日期升序，新活动在上用 desc()
    return render_template('activities.html', activities=activities)

@app.route('/gallery')
def gallery():
    import os
    static_folder = app.static_folder or ''
    image_folder = os.path.join(static_folder, 'history_photos')
    os.makedirs(image_folder, exist_ok=True)
    image_files = [f for f in os.listdir(image_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
    image_urls = [url_for('static', filename=f'history_photos/{img}') for img in image_files]
    return render_template('gallery.html', image_urls=image_urls)

@app.route('/board', methods=['GET', 'POST'])
def board():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '匿名')
        content = request.form.get('content')
        if content:
            msg = Message(nickname=nickname, content=content)
            db.session.add(msg)
            db.session.commit()
        return redirect(url_for('board'))

    # 直接查询，不使用 joinedload
    messages = db.session.query(Message).order_by(Message.timestamp.desc()).all()
    for msg in messages:
        msg.timestamp = msg.timestamp + timedelta(hours=8)
    return render_template('board.html', messages=messages)

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

@app.route('/reply/<int:message_id>', methods=['POST'])
def add_reply(message_id):
    nickname = request.form.get('nickname', '匿名')
    content = request.form.get('content')
    if content:
        reply = Reply(nickname=nickname, content=content, message_id=message_id)
        db.session.add(reply)
        db.session.commit()
    return redirect(url_for('board'))

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
        # 避免重名覆盖
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)