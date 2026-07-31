from app.models import User


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
        sample_user = User.query.get(sample_user.id)
        assert sample_user.username == 'newname123'

    def test_change_password(self, logged_in_client, sample_user):
        response = logged_in_client.post('/profile', data={
            'action': 'change_password',
            'old_password': 'password123',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456'
        }, follow_redirects=True)
        assert response.status_code == 200
        sample_user = User.query.get(sample_user.id)
        assert sample_user.check_password('newpass456') is True
