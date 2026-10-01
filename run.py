"""
南平一中动漫社官网 · 项目启动入口
====================================

本文件是整个应用的启动入口。
它通过导入 create_app() 工厂函数创建 Flask 应用实例，
并在 __main__ 中启动开发服务器。

使用方式：
    python run.py

生产环境建议使用 gunicorn 或其他 WSGI 服务器启动：
    gunicorn run:app

注意：
- 数据库表结构、存储桶、头像迁移等一次性运维操作，请跑 init.py
- 本文件只在 TESTING=1 时执行测试数据初始化
"""

import os
from datetime import datetime, timedelta

from app import create_app, db
from app.models import User, Contest, Candidate

app = create_app()


# ====== 测试环境自动创建测试数据 ======
if os.getenv('TESTING') == '1':
    with app.app_context():
        print("测试模式：正在初始化测试数据...")

        # 内存 SQLite 每次都是空的，需要建表
        db.create_all()

        # 1. 创建测试用户（带后台权限）
        user = User.query.filter_by(username='testuser').first()
        if user:
            user.set_password('password123')
        else:
            user = User(username='testuser', qq='123456789', email='test@qq.com')
            user.set_password('password123')
            user.is_staff = True
            user.is_owner = True
            db.session.add(user)
        db.session.commit()
        print("  - 测试用户已就绪: testuser")

        # 2. 创建测试赛事
        if not Contest.query.filter_by(title='测试赛事').first():
            contest = Contest(
                title='测试赛事',
                description='用于前端自动化测试的赛事',
                type='saimoe',
                gender_mode='separate',
                status='open',
                open_at=datetime.now() - timedelta(days=1),
                close_at=datetime.now() + timedelta(days=50),
                config={}
            )
            db.session.add(contest)
            db.session.commit()
            print(f"  - 创建测试赛事: ID={contest.id}")

            for i in range(5):
                db.session.add(Candidate(
                    contest_id=contest.id,
                    name=f'测试女角色{i}',
                    source='测试作品',
                    gender='female',
                    image_url='https://via.placeholder.com/80/ff6b6b?text=F' + str(i),
                    stage='pending'
                ))
            for i in range(5):
                db.session.add(Candidate(
                    contest_id=contest.id,
                    name=f'测试男角色{i}',
                    source='测试作品',
                    gender='male',
                    image_url='https://via.placeholder.com/80/4dabf7?text=M' + str(i),
                    stage='pending'
                ))
            db.session.commit()
            print("  - 创建候选角色: 女组5个，男组5个")

        db.session.commit()
        print("测试数据初始化完成")
# ====================================


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
