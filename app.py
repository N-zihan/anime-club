import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import session, flash

load_dotenv()

app = Flask(__name__)
app.secret_key = '20090929nzh'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

    messages = db.session.query(Message).order_by(Message.timestamp.desc()).all()
    # 将 UTC 时间转为北京时间 (UTC+8)
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)