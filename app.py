import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

app = Flask(__name__)
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
    activities_list = []
    #活动添加格式：
    #{'title': '活动标题',
    #'date': 'YYYY-MM-DD',
    #'content': '活动内容描述'}
    if not activities_list:
        return render_template('no_activities.html')
    return render_template('activities.html', activities=activities_list)

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)