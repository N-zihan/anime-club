from app.models import User, db
from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import patch


class TestUser:
    """用户中心测试"""

    def test_profile_requires_login(self, client):
        # 未登录应重定向
        response = client.get('/profile', follow_redirects=False)
        assert response.status_code == 302

    def test_profile_page_loads(self, logged_in_client, sample_user):
        response = logged_in_client.get('/profile')
        assert response.status_code == 200
        assert '个人设置' in response.text

    def test_user_profile_page(self, logged_in_client, sample_user):
        response = logged_in_client.get(f'/user?name={sample_user.username}')
        assert response.status_code == 200
        assert sample_user.username in response.text

    def test_user_profile_not_found(self, logged_in_client):
        response = logged_in_client.get('/user?name=nonexistent')
        assert response.status_code == 404

    def test_get_avatar(self, logged_in_client, sample_user):
        response = logged_in_client.get(f'/avatar/{sample_user.id}')
        assert response.status_code == 200

    def test_get_avatar_default(self, logged_in_client):
        response = logged_in_client.get('/avatar/99999')
        assert response.status_code == 404

    def test_change_username(self, logged_in_client, sample_user):
        response = logged_in_client.post('/profile', data={
            'action': 'change_username',
            'new_username': 'newname123'
        }, follow_redirects=True)
        assert response.status_code == 200
        sample_user = db.session.get(User, sample_user.id)
        assert sample_user.username == 'newname123'

    def test_change_password(self, logged_in_client, sample_user):
        response = logged_in_client.post('/profile', data={
            'action': 'change_password',
            'old_password': 'password123',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456'
        }, follow_redirects=True)
        assert response.status_code == 200
        sample_user = db.session.get(User, sample_user.id)
        assert sample_user.check_password('newpass456') is True


# ========== 头像上传、邮箱绑定、用户名冲突 ==========
import io
from unittest.mock import patch


class TestUserExtra:

    def test_change_avatar_success(self, logged_in_client, sample_user, db_session):
        data = {
            'action': 'change_avatar',
            'avatar': (BytesIO(b'fake image data'), 'test.jpg')
        }
        with patch('app.user.compress_image', return_value=b'compressed'):
            resp = logged_in_client.post('/profile', data=data, content_type='multipart/form-data',
                                         follow_redirects=True)
            from app.models import User
            user = db_session.get(User, sample_user.id)
            assert user.avatar is not None
            assert user.avatar_mime == 'image/jpeg'
            assert resp.status_code == 200

    def test_change_avatar_invalid_file(self, logged_in_client, sample_user, db_session):
        data = {
            'action': 'change_avatar',
            'avatar': (BytesIO(b'fake'), 'test.exe')
        }
        resp = logged_in_client.post('/profile', data=data, content_type='multipart/form-data', follow_redirects=True)
        from app.models import User
        user = db_session.get(User, sample_user.id)
        # 头像未被修改（仍为 None）
        assert user.avatar is None
        assert resp.status_code == 200

    def test_change_username_conflict(self, logged_in_client, sample_user, db_session):
        from app.models import User
        # 创建另一个用户
        user2 = User(username='existing', qq='111111111')
        user2.set_password('pass')
        db_session.add(user2)
        db_session.commit()
        resp = logged_in_client.post('/profile', data={
            'action': 'change_username',
            'new_username': 'existing'
        }, follow_redirects=True)
        user = db_session.get(User, sample_user.id)
        # 用户名不应改变
        assert user.username == 'testuser'
        assert resp.status_code == 200

    def test_bind_email_send_code(self, logged_in_client, sample_user):
        with patch('app.user.send_verification_email', return_value=True):
            resp = logged_in_client.post('/profile', data={'action': 'send_email_code', 'email': 'new@qq.com'})
            assert resp.json['success'] is True

    def test_bind_email_verify_code(self, logged_in_client, sample_user, db_session):
        with logged_in_client.session_transaction() as sess:
            sess['profile_email_code'] = '123456'
            sess['profile_pending_email'] = 'new@qq.com'
            sess['profile_email_expires'] = (datetime.now() + timedelta(minutes=5)).isoformat()
        resp = logged_in_client.post('/profile', data={'action': 'verify_email_code', 'code': '123456'})
        assert resp.json['success'] is True
        assert resp.json['email'] == 'new@qq.com'
        from app.models import User
        user = db_session.get(User, sample_user.id)
        assert user.email == 'new@qq.com'
