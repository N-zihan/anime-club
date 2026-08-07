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

from app import create_app, db
from app.utils import get_supabase

app = create_app()
supabase = get_supabase()

with app.app_context():
    # -------- 创建数据库表 --------
    db.create_all()
    print("数据库表检查完成")

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
