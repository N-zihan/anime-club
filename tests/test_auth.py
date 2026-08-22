import os
from app.auth import send_email
from app.models import User, db
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['GROUP_VERIFICATION_CODE'] = 'test_group_code'


class TestAuth:

    def test_register_page_loads(self, client):
        response = client.get('/register')
        assert response.status_code == 200
        assert '社团成员注册' in response.text

    def test_login_page_loads(self, client):
        response = client.get('/login')
        assert response.status_code == 200
        assert '社员登录' in response.text

    def test_register_success(self, client, db_session):
        response = client.post('/register', data={
            'username': 'newuser',
            'qq': '1111122222',
            'email': 'test123@qq.com',
            'group': 'test_group_code',
            'password': 'testpass123',
            'code': '123456'  # 随便填
        }, follow_redirects=True)
        assert response.status_code == 200
        user = User.query.filter_by(username='newuser').first()
        assert user is not None
        assert user.qq == '1111122222'

    def test_register_duplicate_username(self, client, sample_user):
        response = client.post('/register', data={
            'username': sample_user.username,
            'qq': '9999999999',
            'email': 'test456@qq.com',
            'group': 'test_group_code',
            'password': 'testpass123',
            'code': '123456'  # 随便填
        }, follow_redirects=True)
        assert '用户名已被注册' in response.text

    def test_register_invalid_group_code(self, client):
        response = client.post('/register', data={
            'username': 'testuser2',
            'qq': '1111122222',
            'email': 'test789@qq.com',
            'group': 'wrong_code',
            'password': 'testpass123',
            'code': '123456'  # 随便填
        }, follow_redirects=True)
        assert '验证码错误' in response.text

    def test_login_success(self, client, sample_user):
        response = client.post('/login', data={
            'username': sample_user.username,
            'password': 'password123'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_login_wrong_password(self, client, sample_user):
        response = client.post('/login', data={
            'username': sample_user.username,
            'password': 'wrongpass'
        }, follow_redirects=True)
        assert '用户名或密码错误' in response.text

    def test_logout(self, logged_in_client):
        response = logged_in_client.get('/logout', follow_redirects=True)
        assert response.status_code == 200
        assert '已退出登录' in response.text

    def test_delete_account(self, logged_in_client, sample_user):
        response = logged_in_client.post('/delete_account', follow_redirects=True)
        assert response.status_code == 200
        user = db.session.get(User, sample_user.id)
        assert user is None


# ========== 邮箱验证、密码重置等 ==========


class TestAuthExtra:

    def test_send_register_code_success(self, client, db_session):
        with patch('app.auth.send_verification_email', return_value=True):
            resp = client.post('/send_register_code', data={'email': 'new@qq.com'})
            assert resp.status_code == 200
            json_data = resp.get_json()
            assert json_data is not None
            assert json_data['success'] is True

    def test_send_register_code_already_bound(self, client, sample_user, db_session):
        sample_user.email = 'exists@qq.com'
        db_session.commit()
        resp = client.post('/send_register_code', data={'email': 'exists@qq.com'})
        assert resp.status_code == 400
        json_data = resp.get_json()
        assert json_data['error'] == '该邮箱已被绑定'

    def test_forgot_password_with_email(self, client, sample_user, db_session):
        sample_user.email = 'test@qq.com'
        db_session.commit()
        with patch('app.auth.send_reset_email', return_value=True):
            resp = client.post('/forgot_password', data={'qq': sample_user.qq}, follow_redirects=True)
            assert '重置链接已发送' in resp.text

    def test_forgot_password_no_email(self, client, sample_user, db_session):
        sample_user.email = None
        db_session.commit()
        resp = client.post('/forgot_password', data={'qq': sample_user.qq}, follow_redirects=True)
        assert '请先绑定' in resp.text

    def test_forgot_bind_send_code(self, client, sample_user, db_session):
        with client.session_transaction() as sess:
            sess['pending_bind_user_id'] = sample_user.id
        with patch('app.auth.send_verification_email', return_value=True):
            resp = client.post('/forgot_bind_send_code', data={'email': 'bind@qq.com'}, follow_redirects=True)
            assert '验证码已发送' in resp.text

    def test_reset_password_token_expired(self, client, sample_user, db_session):
        sample_user.reset_token = 'expired'
        sample_user.reset_token_expires = datetime.now() - timedelta(hours=2)
        db_session.commit()
        resp = client.get('/reset_password/expired', follow_redirects=True)
        assert '链接已过期' in resp.text

    def test_reset_password_invalid_token(self, client, db_session):
        resp = client.get('/reset_password/invalid', follow_redirects=True)
        assert '链接无效或已过期' in resp.text

    def test_reset_password_success(self, client, sample_user, db_session):
        token = 'valid_token'
        sample_user.reset_token = token
        sample_user.reset_token_expires = datetime.now() + timedelta(hours=1)
        db_session.commit()
        resp = client.post(f'/reset_password/{token}', data={
            'password': 'newpass123',
            'confirm': 'newpass123'
        }, follow_redirects=True)
        assert '密码修改成功' in resp.text
        from app.models import User
        user = db_session.get(User, sample_user.id)
        assert user.check_password('newpass123') is True
