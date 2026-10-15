"""
动漫社官网 · 工具函数模块
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

import hashlib
import hmac
import io
import ipaddress
import os
import socket
import time
import uuid
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image
from dotenv import load_dotenv
from flask import abort, current_app
from supabase import create_client, Client

from .models import db

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

_supabase_client: Client | None = None # pylint: disable=invalid-name


def get_supabase() -> Client:
    """懒加载获取 Supabase 客户端，仅在首次调用时初始化"""
    global _supabase_client # pylint: disable=global-statement
    if _supabase_client is None:
        # 测试环境返回 Mock 客户端
        if os.getenv('TESTING') == '1':
            from unittest.mock import MagicMock # pylint: disable=import-outside-toplevel
            _supabase_client = MagicMock()
            return _supabase_client
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("Supabase 未配置：请检查 SUPABASE_URL 和 SUPABASE_KEY 环境变量")
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# ============================================================
# SSRF 防护：只允许访问公网的 http(s) 地址
# ============================================================

def is_public_http_url(url):
    """校验 URL 是否指向公网 http(s) 地址。

    阻止内网 / 环回 / 链路本地（含云元数据 169.254.169.254）/ 保留地址，
    避免服务端被当成跳板去访问内网。
    """
    try:
        parsed = urlparse(url)
    except (ValueError, AttributeError):
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    except ValueError:
        return False
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def safe_get(url, max_redirects=4, **kwargs):
    """带 SSRF 防护的 requests.get：逐跳校验目标地址。

    返回 requests.Response；地址不合法或重定向过多时返回 None。
    """
    kwargs.pop('allow_redirects', None)
    for _ in range(max_redirects + 1):
        if not is_public_http_url(url):
            return None
        try:
            res = requests.get(url, allow_redirects=False, **kwargs)
        except requests.RequestException:
            return None
        if res.is_redirect and res.headers.get('Location'):
            url = urljoin(url, res.headers['Location'])
            continue
        return res
    return None


# ============================================================
# 邮箱验证码：session 是「签名但未加密」的 cookie，不能存明文
# ============================================================

def code_digest(code):
    """验证码摘要。客户端能自行解出 session 里的明文，故只存摘要。"""
    return hashlib.sha256(f'{current_app.secret_key}:{code}'.encode()).hexdigest()


def code_matches(stored_digest, code):
    if not stored_digest or not code:
        return False
    return hmac.compare_digest(stored_digest, code_digest(code))


_ACTION_THROTTLE = {}


def throttle_ok(key, seconds):
    """进程内简易限流，用于挡住最粗暴的邮件轰炸/验证码枚举循环。

    注意：Serverless 多实例下不是强保证，生产建议再叠加 Flask-Limiter
    或平台级（WAF）限流。
    """
    now = time.monotonic()
    last = _ACTION_THROTTLE.get(key)
    if last is not None and now - last < seconds:
        return False
    if len(_ACTION_THROTTLE) > 5000:  # 防止自身无上限增长
        _ACTION_THROTTLE.clear()
    _ACTION_THROTTLE[key] = now
    return True


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


def upload_avatar_to_storage(user_id, image_data):
    """上传头像到 Supabase Storage，返回公开 URL"""
    supabase = get_supabase()
    filename = f"user_{user_id}_{uuid.uuid4().hex[:8]}.jpg"
    supabase.storage.from_('avatars').upload(
        filename,
        image_data,
        file_options={"content-type": "image/jpeg"}
    )
    return supabase.storage.from_('avatars').get_public_url(filename)
