import pytest

class TestPublic:
    """公共页面测试（所有需要登录的页面均使用 logged_in_client）"""

    def test_splash_page(self, client):
        # splash 是公开的，不需要登录
        response = client.get('/')
        assert response.status_code == 200
        assert '南平一中动漫社' in response.text

    def test_home_page(self, logged_in_client):
        response = logged_in_client.get('/home')
        assert response.status_code == 200
        assert '欢迎来到动漫社' in response.text

    def test_about_page(self, logged_in_client):
        response = logged_in_client.get('/about')
        assert response.status_code == 200
        assert '社团简介' in response.text

    def test_activities_page(self, logged_in_client):
        response = logged_in_client.get('/activities')
        assert response.status_code == 200
        assert '近期活动' in response.text

    def test_gallery_page(self, logged_in_client):
        response = logged_in_client.get('/gallery')
        assert response.status_code == 200
        assert '珍贵历史图片' in response.text

    def test_board_page(self, logged_in_client):
        response = logged_in_client.get('/board')
        assert response.status_code == 200
        assert '社员留言板' in response.text

    def test_anime_resources_page(self, logged_in_client):
        response = logged_in_client.get('/anime_resources')
        assert response.status_code == 200
        assert '番剧资源下载' in response.text

    def test_submit_anime_requires_login(self, client):
        # 未登录应重定向到登录页
        response = client.get('/submit_anime', follow_redirects=False)
        assert response.status_code == 302

    def test_members_page(self, logged_in_client):
        response = logged_in_client.get('/members')
        assert response.status_code == 200
        assert '社员名单' in response.text

    def test_contest_center_page(self, logged_in_client):
        response = logged_in_client.get('/contest_center')
        assert response.status_code == 200
        assert '赛事中心' in response.text

    def test_contest_rules_page(self, logged_in_client, sample_contest):
        response = logged_in_client.get(f'/contest/{sample_contest.id}/rules')
        assert response.status_code == 200
        assert '规则确认' in response.text

    def test_contest_detail_page(self, logged_in_client, sample_contest):
        response = logged_in_client.get(f'/contest/{sample_contest.id}')
        assert response.status_code == 200
        assert '测试萌战' in response.text

    def test_board_post_requires_login(self, client):
        response = client.post('/board', data={'content': 'test'}, follow_redirects=False)
        assert response.status_code == 302

    def test_add_reply_requires_login(self, client, sample_message):
        response = client.post(f'/reply/{sample_message.id}', data={'content': 'test reply'}, follow_redirects=False)
        assert response.status_code == 302