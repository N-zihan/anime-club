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

import io
import os

from PIL import Image
from dotenv import load_dotenv
from flask import abort
from supabase import create_client, Client

from .models import db

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def compress_image(file_data, max_size=(800, 800), quality=85, output_format='JPEG'):
    """
    压缩图片数据
    :param file_data: 原始图片二进制数据
    :param max_size: 最大宽高 (width, height)
    :param quality: JPEG品质 1-100
    :param output_format: 'JPEG' 或 'PNG'
    :return: 压缩后的二进制数据
    """
    img = Image.open(io.BytesIO(file_data))

    # 处理透明背景（PNG转RGB）
    if img.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    # 缩放到指定尺寸（保持宽高比）
    img.thumbnail(max_size, Image.Resampling.LANCZOS)

    output = io.BytesIO()
    img.save(output, format=output_format, quality=quality, optimize=True)
    return output.getvalue()


def get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj
