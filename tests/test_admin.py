import pytest


class TestAdmin:

    def test_admin_entry_redirects_if_not_admin(self, client):
        response = client.get('/admin/entry', follow_redirects=True)
        assert response.status_code == 200

    def test_admin_dashboard_requires_admin(self, logged_in_client):
        # 不 follow 重定向，直接检查状态码和 Location
        response = logged_in_client.get('/admin/dashboard')
        assert response.status_code == 302
        # admin_required 会重定向到 public.index（即 /home）
        assert response.headers['Location'].endswith('/home')

    def test_admin_dashboard_loads_for_admin(self, admin_client):
        response = admin_client.get('/admin/dashboard')
        assert response.status_code == 200
        assert '站长管理面板' in response.text

    def test_admin_users_requires_owner(self, logged_in_client):
        response = logged_in_client.get('/admin/users')
        assert response.status_code == 302
        # 普通用户没有 admin 权限，被 admin_required 拦截跳转到首页
        assert response.headers['Location'].endswith('/home')

    def test_admin_users_loads_for_owner(self, admin_client):
        response = admin_client.get('/admin/users')
        assert response.status_code == 200
        assert '用户管理' in response.text

    def test_admin_activities_loads(self, admin_client):
        response = admin_client.get('/admin/activities')
        assert response.status_code == 200
        assert '活动管理' in response.text

    def test_admin_anime_resources_loads(self, admin_client):
        response = admin_client.get('/admin/anime_resources')
        assert response.status_code == 200
        assert '番剧资源管理' in response.text

    def test_admin_gallery_loads(self, admin_client):
        response = admin_client.get('/admin/gallery')
        assert response.status_code == 200
        assert '照片墙管理' in response.text

    def test_admin_messages_loads(self, admin_client):
        response = admin_client.get('/admin/messages')
        assert response.status_code == 200
        assert '留言管理' in response.text

    def test_admin_contests_manage_loads(self, admin_client):
        response = admin_client.get('/admin/contests/manage')
        assert response.status_code == 200
        assert '赛事管理' in response.text

    def test_admin_contest_create_loads(self, admin_client):
        response = admin_client.get('/admin/contests/create')
        assert response.status_code == 200
        assert '创建赛事' in response.text