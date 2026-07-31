from app.models import User, db


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
            'group': 'test_group_code',
            'password': 'testpass123'
        }, follow_redirects=True)
        assert response.status_code == 200
        user = User.query.filter_by(username='newuser').first()
        assert user is not None
        assert user.qq == '1111122222'

    def test_register_duplicate_username(self, client, sample_user):
        response = client.post('/register', data={
            'username': sample_user.username,
            'qq': '9999999999',
            'group': 'test_group_code',
            'password': 'testpass123'
        }, follow_redirects=True)
        assert '用户名已被注册' in response.text

    def test_register_invalid_group_code(self, client):
        response = client.post('/register', data={
            'username': 'testuser2',
            'qq': '1111122222',
            'group': 'wrong_code',
            'password': 'testpass123'
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
