import io
import pytest
from PIL import Image
from app.models import Activity
from app.utils import compress_image, get_or_404, allowed_file, is_public_http_url
from flask import abort
from unittest.mock import patch


class TestUtils:
    def test_allowed_file_valid(self):
        assert allowed_file('test.jpg') is True
        assert allowed_file('test.png') is True
        assert allowed_file('test.JPG') is True

    def test_allowed_file_invalid(self):
        assert allowed_file('test.exe') is False
        assert allowed_file('test') is False


class TestSsrfGuard:
    """回归：SSRF 白名单校验（内网/环回/云元数据地址一律拒绝）"""

    def test_public_url_allowed(self):
        assert is_public_http_url('https://example.com/a.jpg') is True

    def test_internal_targets_rejected(self):
        assert is_public_http_url('http://169.254.169.254/latest/meta-data/') is False
        assert is_public_http_url('http://127.0.0.1:5000/') is False
        assert is_public_http_url('http://localhost/admin') is False
        assert is_public_http_url('http://10.0.0.5/') is False
        assert is_public_http_url('http://192.168.1.1/') is False

    def test_non_http_schemes_rejected(self):
        assert is_public_http_url('file:///etc/passwd') is False
        assert is_public_http_url('gopher://example.com/') is False
        assert is_public_http_url('') is False

    def test_compress_image_rgba_to_rgb(self):
        # 创建 RGBA 图片
        img = Image.new('RGBA', (100, 100), (255, 0, 0, 128))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        compressed = compress_image(img_bytes.getvalue(), max_size=(50, 50), quality=80)
        assert isinstance(compressed, bytes)
        # 验证压缩后尺寸不超过 50x50
        result_img = Image.open(io.BytesIO(compressed))
        assert result_img.size[0] <= 50
        assert result_img.size[1] <= 50
        # 应为 RGB 模式（JPEG）
        assert result_img.mode == 'RGB'

    def test_compress_image_keep_aspect(self):
        img = Image.new('RGB', (200, 100), (255, 255, 255))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        compressed = compress_image(img_bytes.getvalue(), max_size=(50, 50), quality=80)
        result_img = Image.open(io.BytesIO(compressed))
        # 宽度应缩放到50，高度按比例应为25
        assert result_img.size[0] == 50
        assert result_img.size[1] == 25

    def test_compress_image_invalid_data(self):
        with pytest.raises(Exception):
            compress_image(b'invalid data')

    def test_get_or_404_found(self, db_session, sample_activity):
        obj = get_or_404(Activity, sample_activity.id)
        assert obj.id == sample_activity.id

    def test_get_or_404_not_found(self, app):
        with app.app_context():
            with pytest.raises(Exception):  # abort 抛出 HTTPException
                get_or_404(Activity, 99999)
