"""t2-core 修复项的回归测试（SSRF / 开放重定向 / 引擎边界 / 连接池分流）

对应本轮修复：
1. is_public_http_url 漏判 CGNAT(100.64.0.0/10) 与阿里云 metadata(100.100.100.200)
2. safe_get 复核真实对端 IP（DNS rebinding 第二道防线）
3. notification_read 只允许站内相对跳转
4. get_match_winner 容忍缺失 candidate2 键的轮空场
5. SQLALCHEMY_ENGINE_OPTIONS 只对 Postgres 注入
"""
import ipaddress
from unittest.mock import patch

import pytest

from app import create_app
from app.contest_engine import get_match_winner, is_banned
from app.models import Contest, Candidate, Notification, db
from app.utils import _BLOCKED_NETWORKS, is_public_http_url, safe_get


class TestSsrfBlocklist:
    def test_cgnat_and_metadata_rejected(self):
        # Python 3.14 的 is_private/is_reserved 覆盖不到这两段，必须靠显式黑名单
        assert is_public_http_url('http://100.64.0.1/') is False
        assert is_public_http_url('http://100.100.100.200/latest/meta-data/') is False
        assert is_public_http_url('http://100.127.255.254/') is False

    def test_special_purpose_networks_rejected(self):
        assert is_public_http_url('http://192.0.0.5/') is False
        assert is_public_http_url('http://198.18.0.1/') is False

    def test_public_still_allowed(self):
        assert is_public_http_url('https://example.com/a.jpg') is True

    def test_blocklist_contents(self):
        nets = {str(n) for n in _BLOCKED_NETWORKS}
        assert '100.64.0.0/10' in nets
        assert '100.100.100.200/32' in nets


class TestSafeGetPeerCheck:
    def test_private_peer_not_loopback_fails(self):
        """校验通过但真实对端是内网 → 必须整体失败（DNS rebinding 兜底）"""
        class _Conn:
            sock = type('S', (), {'getpeername': staticmethod(lambda: ('10.0.0.7', 80))})()

        class _Res:
            raw = type('R', (), {'_connection': _Conn()})()
            is_redirect = False
            headers = {}
            closed = False

            def close(self):
                self.closed = True

        with patch('app.utils.requests.get', return_value=_Res()):
            assert safe_get('https://example.com', timeout=1) is None

    def test_loopback_proxy_keeps_redirect_local(self):
        """本地代理（127.0.0.1:7890）视为环境代理，但跳转不得本地跟随"""
        class _Conn:
            sock = type('S', (), {'getpeername': staticmethod(lambda: ('127.0.0.1', 7890))})()

        class _Res:
            raw = type('R', (), {'_connection': _Conn()})()
            is_redirect = True
            headers = {'Location': 'http://169.254.169.254/'}

            def close(self):
                pass

        with patch('app.utils.requests.get', return_value=_Res()):
            res = safe_get('https://example.com', timeout=1)
        # 未跟随重定向，直接返回该响应；下一次调用者若再请求会被逐跳校验挡住
        assert res is not None

    def test_redirect_to_private_is_blocked(self):
        """正常直连下，重定向到内网地址必须被逐跳校验拦下"""
        class _Conn:
            sock = type('S', (), {'getpeername': staticmethod(lambda: ('93.184.216.34', 443))})()

        class _Res:
            raw = type('R', (), {'_connection': _Conn()})()
            is_redirect = True
            headers = {'Location': 'http://127.0.0.1/admin'}

            def close(self):
                pass

        with patch('app.utils.requests.get', return_value=_Res()) as mocked:
            assert safe_get('https://example.com', timeout=1) is None
        # 只请求了一次：第二次目标在内网，被校验阶段挡住
        assert mocked.call_count == 1


class TestNotificationOpenRedirect:
    def _mk(self, db_session, link):
        n = Notification(user_id=1, title='t', content='c', type='system', link=link)
        db_session.add(n)
        db_session.commit()
        return n.id

    @pytest.mark.parametrize('link', ['https://evil.example.com/x', '//evil.example.com/x'])
    def test_external_link_falls_back(self, app, db_session, link):
        nid = self._mk(db_session, link)
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_role'] = 'member'
        resp = client.get(f'/notifications/read/{nid}')
        assert resp.status_code == 302
        assert '/notifications' in resp.headers['Location']
        assert 'evil.example.com' not in resp.headers['Location']

    def test_internal_link_allowed(self, app, db_session):
        nid = self._mk(db_session, '/home')
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_role'] = 'member'
        resp = client.get(f'/notifications/read/{nid}')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/home')


class TestEngineBoundary:
    def test_bye_match_missing_candidate2_key(self, db_session, sample_contest):
        """轮空场可能只带 candidate1，缺 candidate2 键时不得 KeyError"""
        cand = Candidate(contest_id=sample_contest.id, name='轮空角色', source='作品',
                         gender='female', stage='knockout')
        db_session.add(cand)
        db_session.commit()
        match = {'candidate1': cand.id, 'bye': True, 'status': 'active'}
        assert get_match_winner(sample_contest, match, 'female', 1) == cand.id

    def test_missing_candidate_is_treated_as_unavailable(self, db_session, sample_contest):
        cand = Candidate(contest_id=sample_contest.id, name='存在角色', source='作品',
                         gender='female', stage='knockout')
        db_session.add(cand)
        db_session.commit()
        # candidate1 不存在（已被删除的竞态）：不得把不存在的角色判为胜者
        assert get_match_winner(sample_contest, {'candidate1': 999999, 'candidate2': cand.id},
                                'female', 1) == cand.id
        assert is_banned(999999, sample_contest.id) is True


class TestEngineOptionsScope:
    def test_sqlite_url_gets_no_pool_options(self, monkeypatch):
        # sqlite 不支持 pool_size/max_overflow，注入会让引擎直接报错
        # （Flask-SQLAlchemy 会把该键设为 {}，故判空而非判缺失）
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
        app = create_app()
        assert not app.config.get('SQLALCHEMY_ENGINE_OPTIONS')

    def test_postgres_gets_serverless_pool(self, monkeypatch):
        monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@host:6543/postgres')
        app = create_app()
        opts = app.config['SQLALCHEMY_ENGINE_OPTIONS']
        assert opts['pool_pre_ping'] is True
        assert opts['pool_size'] == 1
        assert opts['max_overflow'] == 2
        assert opts['pool_recycle'] == 300
