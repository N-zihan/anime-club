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

注意：开发模式下 debug=False，如需调试请手动修改。
"""

import os
from datetime import datetime, timedelta

from app import create_app, db
from app.models import User, Contest, Candidate
from app.utils import get_supabase

app = create_app()

with app.app_context():
    supabase = get_supabase()
    # -------- 创建数据库表 --------
    db.create_all()
    print("数据库表检查完成")

    # ====== 测试环境自动创建测试数据 ======
    if os.getenv('TESTING') == '1':
        print("测试模式：正在初始化测试数据...")

        # 1. 创建测试用户（带后台权限）
        user = User.query.filter_by(username='testuser').first()
        if user:
            user.set_password('password123')
        else:
            user = User(username='testuser', qq='123456789', email='test@qq.com')
            user.set_password('password123')
            user.is_staff = True  # 运营权限
            user.is_owner = True  # 站长权限
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

            # 3. 添加候选角色（女组5个，男组5个）
            for i in range(5):
                c = Candidate(
                    contest_id=contest.id,
                    name=f'测试女角色{i}',
                    source='测试作品',
                    gender='female',
                    image_url='https://via.placeholder.com/80/ff6b6b?text=F' + str(i),
                    stage='pending'
                )
                db.session.add(c)
            for i in range(5):
                c = Candidate(
                    contest_id=contest.id,
                    name=f'测试男角色{i}',
                    source='测试作品',
                    gender='male',
                    image_url='https://via.placeholder.com/80/4dabf7?text=M' + str(i),
                    stage='pending'
                )
                db.session.add(c)
            db.session.commit()
            print("  - 创建候选角色: 女组5个，男组5个")

        db.session.commit()
        print("测试数据初始化完成")
    # ====================================

    # -------- 创建 Supabase 存储桶 --------
    try:
        # 获取已有桶列表（兼容字典和对象两种格式）
        existing_buckets_raw = supabase.storage.list_buckets()
        existing_bucket_names = []
        for b in existing_buckets_raw:
            if isinstance(b, dict):
                existing_bucket_names.append(b.get('name'))
            else:
                existing_bucket_names.append(getattr(b, 'name', None))

        required_buckets = ['photos', 'contest_images']

        for bucket in required_buckets:
            if bucket not in existing_bucket_names:
                supabase.storage.create_bucket(bucket, public=True)
                print(f"已创建存储桶: {bucket}")
            else:
                print(f"存储桶已存在: {bucket}")
    except Exception as e:
        print(f"存储桶初始化跳过: {e}")
        import traceback

        traceback.print_exc()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
