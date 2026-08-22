import io
import pytest
from PIL import Image
from app.models import Activity
from app.utils import compress_image, get_or_404, allowed_file
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
