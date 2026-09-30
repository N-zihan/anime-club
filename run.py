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
"""

import os
from datetime import datetime, timedelta

from sqlalchemy import inspect, text

from app import create_app, db
from app.models import User, Contest, Candidate
from app.utils import get_supabase

app = create_app()


def ensure_columns():
    """对比 models.py 定义和数据库实际结构，自动补齐缺失的列。
    只加列，不改类型、不删列（那些操作仍需手动处理）。
    """
    inspector = inspect(db.engine)
    dialect = db.engine.dialect
    existing_tables = set(inspector.get_table_names())

    for table_name, table in db.metadata.tables.items():
        if table_name not in existing_tables:
            # 新表交给 create_all 处理
            continue

        existing_cols = {c['name'] for c in inspector.get_columns(table_name)}

        for column in table.columns:
            col_name = column.name
            if col_name in existing_cols:
                continue
            # 主键列不存在的情况不可能发生（表建好就一定有主键）
            if column.primary_key:
                continue

            col_type = column.type.compile(dialect=dialect)
            ddl = f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {col_type}'

            # nullable 和 default
            if not column.nullable:
                # 已有数据时加非空列需要默认值，这里只做尽力而为
                if column.default is not None and column.default.arg is not None:
                    default_val = column.default.arg
                    if callable(default_val):
                        default_val = default_val()
                    if isinstance(default_val, str):
                        ddl += f" DEFAULT '{default_val}'"
                    elif isinstance(default_val, bool):
                        ddl += f" DEFAULT {str(default_val).upper()}"
                    else:
                        ddl += f' DEFAULT {default_val}'

            try:
                db.session.execute(text(ddl))
                print(f'已添加列: {table_name}.{col_name} ({col_type})')
            except Exception as e:
                print(f'添加列 {table_name}.{col_name} 失败: {e}')
                db.session.rollback()

    db.session.commit()


with app.app_context():
    supabase = get_supabase()
    # -------- 创建数据库表 --------
    db.create_all()
    print("数据库表检查完成")

    # ====== 自动补齐缺失的列 ======
    ensure_columns()
    # =============================

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

        required_buckets = ['photos', 'contest_images', 'avatars']

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
