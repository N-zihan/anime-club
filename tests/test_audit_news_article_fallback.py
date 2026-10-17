"""T5 独立复检 · 番剧新闻详情页空值/降级兜底 + 模板层 XSS 验证

Lead 追加要求：
  a) T3 实现后，'videos' 字段为空/缺失时详情页模板不得崩；
  b) get_article_content 返回 None 时详情页要有明确降级行为；
  c) 模板层对非白名单视频 URL 绝不能输出成可执行 iframe。

本文件用**真实 Flask 路由 + 真实 Jinja 环境（含 base.html 继承）**验证，
而不是孤立 Jinja 环境，避免「模板单独渲染 OK 但真实页面 500」的漏检。

★ 本文件曾在 2026-10-17 之间被外部删除（只剩 .pyc），已由 T5 重建。
"""
import pytest

from app import anime_news


@pytest.fixture
def patched_detail(monkeypatch):
    """打桩抓取层，避免任何外网请求。"""
    def _set(payload):
        monkeypatch.setattr(anime_news, 'get_article_content', lambda url: payload,
                            raising=False)
        # public.py 在函数内 from .anime_news import get_article_content，同样被打桩
    return _set


_VALID_URL = 'https://news.nanyi-anime-club.top/post/1'


def test_route_renders_200_when_fetch_returns_none(client, patched_detail):
    """抓取失败（None）时详情页必须降级渲染而不是 500。"""
    patched_detail(None)
    resp = client.get('/anime_news/article', query_string={'url': _VALID_URL})
    assert resp.status_code == 200, f'降级失败，HTTP {resp.status_code}'
    body = resp.get_data(as_text=True)
    assert 'anime_news' in body or '返回' in body


def test_route_renders_200_when_videos_key_missing(client, patched_detail):
    """T3 之前的返回结构（无 videos 键）也必须能渲染。"""
    patched_detail({'title': 'T', 'content': 'x' * 200, 'images': []})
    resp = client.get('/anime_news/article', query_string={'url': _VALID_URL})
    assert resp.status_code == 200


@pytest.mark.parametrize('videos', [
    [],
    None,
    [{}],
    [{'url': None}],
    [{'url': ''}],
    [{'src': 'https://www.youtube.com/embed/a'}],
])
def test_route_renders_200_for_degenerate_videos(client, patched_detail, videos):
    """videos 为 空/None/元素缺字段 时不得抛异常。"""
    patched_detail({'title': 'T', 'content': 'y' * 200, 'images': [], 'videos': videos})
    resp = client.get('/anime_news/article', query_string={'url': _VALID_URL})
    assert resp.status_code == 200, f'videos={videos!r} 导致 HTTP {resp.status_code}'


def test_route_rejects_invalid_url(client):
    """url 参数缺失或非公网时必须是 404/400，不得进入抓取。"""
    assert client.get('/anime_news/article').status_code == 404
    assert client.get('/anime_news/article',
                      query_string={'url': 'javascript:alert(1)'}).status_code == 404
    assert client.get('/anime_news/article',
                      query_string={'url': 'http://127.0.0.1:8000/x'}).status_code == 404


def test_api_detail_returns_error_when_fetch_none(client, patched_detail):
    """API 在抓取失败时应返回错误 JSON 而不是 500。"""
    patched_detail(None)
    resp = client.get('/api/anime/news-detail', query_string={'url': _VALID_URL})
    assert resp.status_code in (404, 502, 503), f'意外状态码 {resp.status_code}'
    assert resp.is_json, 'API 必须返回 JSON 错误体'


def test_api_detail_rejects_private_url(client):
    """API 必须挡住内网地址（SSRF）。"""
    for bad in ('http://169.254.169.254/latest/meta-data/',
                'http://localhost:5000/',
                'file:///etc/passwd'):
        resp = client.get('/api/anime/news-detail', query_string={'url': bad})
        assert resp.status_code == 400, f'{bad} 未被挡住，HTTP {resp.status_code}'


# ---------------------------------------------------------------------------
# 模板层：即使解析层漏了，模板也绝不能把非白名单 URL 渲染成可执行 iframe
# ---------------------------------------------------------------------------
def _render_detail(app, **ctx):
    from flask import render_template
    with app.test_request_context('/anime_news/article', query_string={'url': _VALID_URL}):
        return render_template('anime_news_detail.html', **ctx)


@pytest.mark.parametrize('evil', [
    'https://evil.example.com/embed/x',
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'https://attacker.test/x.mp4',
])
def test_template_never_emits_evil_iframe(app, evil):
    """把恶意 URL 塞进 videos，模板输出里不得出现它的 iframe。"""
    html = _render_detail(
        app, article=None, url=_VALID_URL, content='c' * 200, images=[],
        source_zh='测试', videos=[{'url': evil, 'type': 'iframe'}],
    )
    lowered = html.lower()
    assert 'javascript:alert(1)' not in lowered, '模板直接输出了 javascript: 伪协议'
    assert 'data:text/html' not in lowered, '模板直接输出了 data: URL'
    # 若 evil 被渲染，只能作为 <a href> 外链，不能是 <iframe src>
    import re
    for m in re.finditer(r'<iframe[^>]*>', html, re.I | re.S):
        tag = m.group(0)
        assert 'evil.example.com' not in tag, f'非白名单域被渲染成 iframe: {tag}'
        assert 'javascript:' not in tag.lower(), f'iframe 中含伪协议: {tag}'
        assert 'attacker.test' not in tag, f'非白名单域被渲染成 iframe: {tag}'


def test_template_escapes_video_url_in_href(app):
    """外链形式输出时，URL 必须被 Jinja 转义（双引号不得逃逸）。"""
    evil = 'https://evil.example.com/x" onload="alert(1)'
    html = _render_detail(
        app, article=None, url=_VALID_URL, content='c' * 200, images=[],
        source_zh='测试', videos=[{'url': evil, 'type': 'video'}],
    )
    assert 'onload="alert(1)"' not in html, '属性逃逸成功：onload 未被转义'
    assert '" onload=' not in html, '属性逃逸成功：引号未转义'
