"""
南平一中动漫社官网 · 工具函数模块
====================================

本模块提供全局工具函数和第三方服务客户端初始化：

1. Supabase 客户端：
   - 从环境变量读取 URL 和密钥
   - 用于照片文件的上传、删除、获取公开链接

2. 文件类型校验：
   - allowed_file() 函数检查文件扩展名
   - 仅允许 png, jpg, jpeg, gif 四种格式
   - 用于头像上传和照片上传

本模块是整个项目中唯一与 Supabase SDK 直接交互的地方。
"""

import os

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
