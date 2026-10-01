"""
一次性运维脚本：建表、补列、建桶。
部署前后手动跑一次，不要挂在 run.py 里。
"""
from sqlalchemy import inspect, text

from app import create_app, db
from app.utils import get_supabase

app = create_app()


def ensure_columns():
    """对比 models.py 和数据库，自动补缺失的列"""
    inspector = inspect(db.engine)
    dialect = db.engine.dialect
    existing_tables = set(inspector.get_table_names())

    for table_name, table in db.metadata.tables.items():
        if table_name not in existing_tables:
            continue
        existing_cols = {c['name'] for c in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing_cols or column.primary_key:
                continue
            col_type = column.type.compile(dialect=dialect)
            ddl = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}'
            try:
                db.session.execute(text(ddl))
                print(f'已添加列: {table_name}.{column.name}')
            except Exception as e:
                print(f'添加列失败: {e}')
                db.session.rollback()
    db.session.commit()


def ensure_buckets():
    """检查并创建存储桶"""
    supabase = get_supabase()
    existing = supabase.storage.list_buckets()
    names = []
    for b in existing:
        if isinstance(b, dict):
            names.append(b.get('name'))
        else:
            names.append(getattr(b, 'name', None))
    for bucket in ['photos', 'contest_images', 'avatars']:
        if bucket in names:
            print(f'存储桶已存在: {bucket}')
        else:
            supabase.storage.create_bucket(bucket, options={'public': True})
            print(f'已创建: {bucket}')


with app.app_context():
    print('=== 初始化开始 ===')
    db.create_all()
    print('表检查完成')
    ensure_columns()
    ensure_buckets()
    print('=== 初始化完成 ===')
