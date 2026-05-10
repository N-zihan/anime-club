import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime, timezone   # 修改 1：导入 timezone

load_dotenv()

app = Flask(__name__)

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# 定义留言板数据模型
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=False, default='匿名')
    content = db.Column(db.Text, nullable=False)
    # 修改 2：使用 timezone-aware 的 UTC 时间
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Message {self.nickname}>'


# 创建数据库表
with app.app_context():
    db.create_all()


# ========== 路由 ==========

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/activities')
def activities():
    activities_list = []
    if not activities_list:
        return render_template('no_activities.html')
    return render_template('activities.html', activities=activities_list)


@app.route('/gallery')
def gallery():
    # 修改 3：安全处理 static_folder 可能为 None 的情况
    static_folder = app.static_folder or ''
    image_folder = os.path.join(static_folder, 'history_photos')
    # 修改 4：使用 exist_ok=True 避免目录已存在时报错
    os.makedirs(image_folder, exist_ok=True)

    image_files = [f for f in os.listdir(image_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
    image_urls = [url_for('static', filename=f'history_photos/{img}') for img in image_files]
    return render_template('gallery.html', image_urls=image_urls)


# ========== 留言板路由 ==========
@app.route('/board', methods=['GET', 'POST'])
def board():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '匿名')
        content = request.form.get('content')
        if content:
            new_message = Message(nickname=nickname, content=content)
            db.session.add(new_message)
            db.session.commit()
        return redirect(url_for('board'))

    # 修改 5：使用 db.session.query 代替 Message.query 消除类型警告
    messages = db.session.query(Message).order_by(Message.timestamp.desc()).all()
    return render_template('board.html', messages=messages)


# ========== 启动 ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)