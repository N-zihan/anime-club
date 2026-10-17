"""T5 独立复检 · DNS rebinding / 重定向逐跳校验对抗测试

验证点：
  1) 第 1 跳公网 → 第 2 跳重定向到内网：必须整体失败（不能跟随）
  2) 每一跳都执行 resolve_public_ip（不是只在首跳校验）
  3) 重定向次数上限仍然生效（无限重定向不能死循环）
  4) 对端 IP 复核（_peer_is_public）确实被调用

全部用 monkeypatch，不发起真实网络请求。
"""
import sys

import pytest

sys.path.insert(0, r"C:\Users\NZH\Desktop\动漫社网站")

import app.utils as utils  # noqa: E402


class _FakeResp:
    def __init__(self, location=None, peer=("93.184.216.34", 443), status=200):
        self.status_code = status
        self.headers = {"Location": location} if location else {}
        self.is_redirect = location is not None
        self._peer = peer
        self.closed = False

    @property
    def raw(self):
        class _Conn:
            sock = None
        return _Conn()

    def close(self):
        self.closed = True


def test_redirect_to_internal_is_blocked(monkeypatch):
    """第 1 跳公网、第 2 跳内网 → 必须失败，不能跟随到内网。"""
    requested = []

    def fake_get(url, **kw):
        requested.append(url)
        if 'public.example.com' in url:
            return _FakeResp(location='http://169.254.169.254/latest/meta-data/')
        return _FakeResp()  # 内网响应（不应到达）

    monkeypatch.setattr(utils.requests, 'get', fake_get)
    res = utils.safe_get('https://public.example.com/page')
    print(f'\n请求过的 URL: {requested}')
    assert res is None, '重定向到内网未被拦截！'
    assert not any('169.254.169.254' in u for u in requested), \
        f'竟然真的请求了内网地址（SSRF 成功）: {requested}'


def test_every_hop_is_validated(monkeypatch):
    """每一跳都必须做 resolve_public_ip 校验（不是只校验首跳）。"""
    hops = []

    def fake_resolve(host, port):
        hops.append(host)
        return '93.184.216.34'

    def fake_get(url, **kw):
        if url.endswith('/a'):
            return _FakeResp(location='https://b.example.com/b')
        if url.endswith('/b'):
            return _FakeResp(location='https://c.example.com/c')
        return _FakeResp()

    monkeypatch.setattr(utils, 'resolve_public_ip', fake_resolve)
    monkeypatch.setattr(utils.requests, 'get', fake_get)
    res = utils.safe_get('https://a.example.com/a')
    print(f'\n校验过的主机序列: {hops}')
    assert hops == ['a.example.com', 'b.example.com', 'c.example.com'], \
        f'并非每一跳都校验: {hops}'
    assert res is not None


def test_peer_ip_recheck_is_invoked(monkeypatch):
    """_peer_is_public 对端复核必须被调用（DNS rebinding 第二道防线）。"""
    calls = []
    orig = utils._peer_is_public

    def spy(response, expected_port):
        calls.append(expected_port)
        return orig(response, expected_port)

    # 必须打桩 DNS，否则假域名解析失败会提前返回，测不到对端复核
    monkeypatch.setattr(utils, 'resolve_public_ip', lambda h, p: '93.184.216.34')
    monkeypatch.setattr(utils, '_peer_is_public', spy)
    monkeypatch.setattr(utils.requests, 'get', lambda url, **kw: _FakeResp())
    utils.safe_get('https://a.example.com/a')
    assert calls, '_peer_is_public 未被调用，对端复核缺失'


def test_redirect_limit_still_enforced(monkeypatch):
    """无限重定向必须被 max_redirects 截断，不能死循环。"""
    count = [0]

    monkeypatch.setattr(utils, 'resolve_public_ip', lambda h, p: '93.184.216.34')

    def fake_get(url, **kw):
        count[0] += 1
        return _FakeResp(location=f'https://loop.example.com/{count[0]}')

    monkeypatch.setattr(utils.requests, 'get', fake_get)
    res = utils.safe_get('https://loop.example.com/0', max_redirects=4)
    print(f'\n重定向请求次数: {count[0]}')
    assert res is None, '无限重定向未被截断'
    assert count[0] == 5, f'max_redirects=4 应最多请求 5 次，实际 {count[0]}'


def test_internal_first_hop_blocked_without_any_request(monkeypatch):
    """首跳就是内网时，连一次请求都不该发。"""
    sent = []
    monkeypatch.setattr(utils.requests, 'get',
                        lambda url, **kw: sent.append(url) or _FakeResp())
    assert utils.safe_get('http://100.100.100.200/') is None
    assert utils.safe_get('http://100.64.0.1/') is None
    assert sent == [], f'内网地址竟然发出了请求: {sent}'


@pytest.mark.parametrize('url', [
    'http://100.100.100.200/',
    'http://100.64.0.1/',
    'http://[::ffff:100.100.100.200]/',
    'http://2130706433/',
    'http://0x7f000001/',
])
def test_high_risk_addresses_return_none(monkeypatch, url):
    """高危地址经 safe_get 必须返回 None（端到端行为，不只判定函数）。"""
    monkeypatch.setattr(utils.requests, 'get',
                        lambda u, **kw: (_ for _ in ()).throw(
                            AssertionError(f'不该请求 {u}')))
    assert utils.safe_get(url) is None, f'{url} 未被 safe_get 拦截'
