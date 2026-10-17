"""T3 单元测试 · 番剧新闻视频提取 + URL 白名单 + 缓存上限

覆盖任务要求的四类正常情况（白名单 iframe / 非白名单 iframe / video+source /
og:video），外加 URL 解析器差异（parser confusion）、伪协议、属性逃逸等恶意输入，
以及本轮修复的「上游抖动把语料覆盖成空」和「搜索缓存无上限」两个真实缺陷。

设计原则：全部用桩替换网络与翻译，测试不依赖外网，也不产生任何真实请求。
"""
import threading
import time

import pytest

from app import anime_news

_FILLER = (
    '<p>This is a sufficiently long filler paragraph used to satisfy the '
    'minimum content length requirement of the article extractor.</p>'
    '<p>Another equally long filler paragraph so that translation and length '
    'checks both pass without any network access at all.</p>'
)


def _article(body, head=''):
    return (f'<html><head><title>视频测试</title>{head}</head>'
            f'<body><article>{_FILLER}{body}</article></body></html>')


@pytest.fixture
def parse(monkeypatch):
    """纯解析入口：打桩 safe_get / 翻译，返回 (result, requested_urls)"""
    requested = []
    pending = {'html': ''}

    class _Res:
        status_code = 200

        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    def fake_safe_get(url, **kwargs):
        # 解析期间只允许请求文章自身；任何额外请求都说明存在由 HTML 触发的 SSRF
        requested.append(url)
        return _Res(pending['html'])

    monkeypatch.setattr(anime_news, 'safe_get', fake_safe_get, raising=False)
    monkeypatch.setattr(anime_news, '_translate_article', lambda text: text, raising=False)
    monkeypatch.setattr(anime_news, '_aliyun_call', lambda *a, **k: None, raising=False)
    anime_news._article_cache.clear()

    def _parse(body, head=''):
        pending['html'] = _article(body, head)
        result = anime_news.get_article_content('https://news.nanyi-anime-club.top/unit-case')
        assert result is not None, '正文骨架应满足长度要求，解析不应返回 None'
        return result

    _parse.requested = requested
    yield _parse
    anime_news._article_cache.clear()


def _urls(result):
    urls = []
    for v in result.get('videos') or []:
        if isinstance(v, dict):
            urls.append(v.get('url') or v.get('src') or '')
        else:
            urls.append(str(v))
    return urls


def _embeds(result):
    return [v.get('url') for v in (result.get('videos') or [])
            if isinstance(v, dict) and v.get('embed')]


# ===========================================================================
# 1) 向后兼容：原有字段必须原样保留
# ===========================================================================
def test_backward_compatible_fields(parse):
    result = parse('<iframe src="https://www.youtube.com/embed/a"></iframe>')
    assert set(result) >= {'title', 'content', 'images', 'videos'}
    assert isinstance(result['images'], list)
    assert isinstance(result['videos'], list)
    assert len(result['content']) >= 100
    # 旧调用方只读 content/images，绝不能因为新增字段而变成别的类型
    assert isinstance(result['content'], str)


def test_old_structure_without_videos_key_still_renders(client, monkeypatch):
    """T3 之前的返回结构（无 videos 键）也必须能走通详情页"""
    monkeypatch.setattr(anime_news, 'get_article_content',
                        lambda url: {'title': 'T', 'content': 'x' * 200, 'images': []},
                        raising=False)
    resp = client.get('/anime_news/article',
                      query_string={'url': 'https://news.nanyi-anime-club.top/p/1'})
    assert resp.status_code == 200
    assert '视频' not in resp.get_data(as_text=True)


# ===========================================================================
# 2) 白名单 iframe 应被提取且 embed=True
# ===========================================================================
@pytest.mark.parametrize('src', [
    'https://www.youtube.com/embed/dQw4w9WgXcQ',
    'https://www.youtube-nocookie.com/embed/a',
    'https://player.bilibili.com/player.html?bvid=BV1xx411c7mD',
    'https://player.vimeo.com/video/123456789',
    'https://www.dailymotion.com/embed/video/x1',
])
def test_whitelist_iframe_extracted_and_embeddable(parse, src):
    result = parse(f'<iframe src="{src}"></iframe>')
    assert src in _urls(result), f'白名单 iframe 未被提取: {src}'
    assert any(src in u for u in _embeds(result)), f'白名单 iframe 未标为可嵌入: {src}'


# ===========================================================================
# 3) 非白名单 iframe：不得标为可嵌入
# ===========================================================================
@pytest.mark.parametrize('src', [
    'https://evil.example.com/embed/x',
    'https://notyoutube.com/embed/x',
    'https://youtube.com.evil.test/embed/x',
    'https://notyoutube.com.evil.test/embed/x',
    'https://evil-youtube.com/embed/x',
])
def test_non_whitelist_iframe_not_embeddable(parse, src):
    result = parse(f'<iframe src="{src}"></iframe>')
    assert _embeds(result) == [], f'非白名单 iframe 被标为可嵌入: {_embeds(result)}'


# ===========================================================================
# 4) <video> / <source> 提取
# ===========================================================================
def test_video_source_extracted_as_external(parse):
    body = ('<video controls poster="https://evil.example.com/p.jpg">'
            '<source src="https://cdn.example.com/movie.mp4" type="video/mp4">'
            '</video>')
    result = parse(body)
    urls = _urls(result)
    assert 'https://cdn.example.com/movie.mp4' in urls, f'<source src> 未提取: {urls}'
    # 视频直链只能外链播放，绝不嵌入
    assert _embeds(result) == [], '视频直链不应被标为可嵌入 iframe'


def test_video_tag_src_extracted(parse):
    result = parse('<video src="https://cdn.example.com/clip.webm"></video>')
    assert 'https://cdn.example.com/clip.webm' in _urls(result)


def test_m3u8_direct_link_extracted(parse):
    """HLS(m3u8) 是外链播放，不应被当成可嵌入 iframe（本站不做转码/代理）"""
    result = parse('<video><source src="https://cdn.example.com/live/master.m3u8"></video>')
    assert 'https://cdn.example.com/live/master.m3u8' in _urls(result)
    assert _embeds(result) == []


# ===========================================================================
# 5) og:video / og:video:url / og:video:secure_url / twitter:player
# ===========================================================================
@pytest.mark.parametrize('prop', ['og:video', 'og:video:url', 'og:video:secure_url',
                                  'twitter:player'])
def test_meta_video_extracted(parse, prop):
    src = 'https://cdn.example.com/trailer.mp4'
    result = parse('', head=f'<meta property="{prop}" content="{src}">')
    assert src in _urls(result), f'{prop} 未提取: {_urls(result)}'


def test_meta_video_whitelist_player_is_embeddable(parse):
    src = 'https://www.youtube.com/embed/a'
    result = parse('', head=f'<meta property="og:video" content="{src}">')
    assert src in _embeds(result)


def test_source_site_youtube_handler_is_converted(parse):
    """真实案例（Anime Corner）：视频藏在**原文站自家域名**的
    youtube-iframe-handler.html?yt_embed=XXXX 里。

    这类页面跑在原站域上、无法在站外嵌入（X-Frame-Options），必须只取
    yt_embed 视频 ID 换成标准 YouTube 播放器地址；同时原站域本身绝不能被
    当成可嵌入域（否则就是把任意第三方页面嵌进本站）。
    """
    handler = 'https://animecorner.me/acwp-direct/youtube-iframe-handler.html?yt_embed=T4S-2lR-164'
    result = parse(f'<iframe src="{handler}"></iframe>')
    urls = _urls(result)
    assert 'https://www.youtube.com/embed/T4S-2lR-164' in urls, \
        f'handler 页未被转换成标准 YouTube 播放器地址: {urls}'
    assert handler not in urls, '原站 handler 地址不应作为可嵌入地址返回'
    assert handler not in _embeds(result), '原站域不得被标为可嵌入'


def test_malicious_yt_embed_param_cannot_inject(parse):
    """yt_embed 参数必须严格是视频 ID 形态，否则不得拼进 embed 地址"""
    for bad in ('javascript:alert(1)', '../../evil', 'a"onload="alert(1)',
                '<script>alert(1)</script>'):
        handler = f'https://animecorner.me/acwp-direct/youtube-iframe-handler.html?yt_embed={bad}'
        result = parse(f'<iframe src="{handler}"></iframe>')
        blob = repr(result)
        for url in _urls(result):
            assert 'javascript:' not in url.lower()
            assert 'onload' not in url.lower()
        assert 'onload' not in blob, f'恶意 yt_embed 污染了结果: {blob[:300]}'


# ===========================================================================
# 6) 伪协议与恶意输入一律整条丢弃
# ===========================================================================
@pytest.mark.parametrize('src', [
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'java\tscript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==',
    'vbscript:msgbox(1)',
    'file:///etc/passwd',
    'blob:https://evil.example.com/uuid',
    '//evil.example.com/x',
    '\\\\evil.example.com\\x',
])
def test_pseudo_protocol_dropped(parse, src):
    result = parse(f'<iframe src="{src}"></iframe>')
    assert _urls(result) == [], f'伪协议未被整条丢弃: {_urls(result)}'


@pytest.mark.parametrize('src', [
    'https://www.youtube.com:evil.example.com/embed/x',   # 伪端口
    'https://www.youtube.com@evil.example.com/embed',     # userinfo 混淆
    'https://user:pass@www.youtube.com/embed/x',          # 合法域但带凭据也不收
    'https://www.youtube.com#@evil.example.com',          # 脏东西藏在 fragment
    'https://www.youtube.com:99999/embed/x',              # 非法端口
])
def test_netloc_parser_confusion_dropped(parse, src):
    """URL 解析器差异（parser confusion）：畸形 netloc 一律整条丢弃"""
    result = parse(f'<iframe src="{src}"></iframe>')
    assert _urls(result) == [], f'畸形 netloc 未被丢弃: {_urls(result)}'


@pytest.mark.parametrize('body', [
    '<iframe src="https://evil.example.com/x" onload="alert(1)"></iframe>',
    '<iframe src=https://evil.example.com/x onload=alert(1)></iframe>',
    '<iframe src="https://www.youtube.com/embed/a" onload="alert(1)"></iframe>',
    # HTML 实体残留绕过：BeautifulSoup 把 &amp;quot; 解成 &quot;
    '<iframe src="https://www.youtube.com/embed/a&amp;quot; onload=&amp;quot;alert(1)"></iframe>',
    '<video src="x" onerror="alert(1)"><source src="y" onerror="alert(2)"></video>',
])
def test_attribute_escape_never_leaks(parse, body):
    result = parse(body)
    assert 'onload' not in repr(result), 'onload 残留进结果'
    assert 'onerror' not in repr(result), 'onerror 残留进结果'
    for url in _urls(result):
        assert not any(c in url for c in '"\'`<>'), f'URL 含可逃逸字符: {url!r}'


@pytest.mark.parametrize('body', [
    '<IFRAME SRC="https://www.youtube.com/embed/a"></IFRAME>',
    '<IfRaMe SrC="javascript:alert(1)"></IfRaMe>',
])
def test_case_insensitive_tags(parse, body):
    result = parse(body)
    assert 'javascript:' not in ' '.join(_urls(result)).lower()


def test_normal_query_string_not_killed(parse):
    """`&` 在查询串里合法，不能被误杀（YouTube 的 ?si=&t= 很常见）"""
    src = 'https://www.youtube.com/embed/a?si=xyz123&t=30'
    result = parse(f'<iframe src="{src}"></iframe>')
    assert src in _urls(result)
    assert src in _embeds(result)


# ===========================================================================
# 7) 解析过程不得产生任何由 HTML 触发的额外请求（SSRF）
# ===========================================================================
def test_no_ssrf_during_parse(parse):
    parse('<iframe src="https://www.youtube.com/embed/a"></iframe>'
          '<iframe src="https://attacker.example.com/probe"></iframe>'
          '<video><source src="https://internal.corp.local/secret.mp4"></video>'
          '<img src="http://169.254.169.254/latest/meta-data/">')
    external = [u for u in parse.requested
                if u != 'https://news.nanyi-anime-club.top/unit-case']
    assert external == [], f'解析期产生了额外请求: {external}'


# ===========================================================================
# 8) 模板层：白名单才嵌入、非白名单只外链、绝不 |safe
# ===========================================================================
def _render(app, **ctx):
    from flask import render_template
    with app.test_request_context('/anime_news/article'):
        base = dict(article=None, url='https://news.nanyi-anime-club.top/p/1',
                    content='c' * 200, images=[], source_zh='测试')
        base.update(ctx)
        return render_template('anime_news_detail.html', **base)


def test_template_renders_whitelist_iframe(app):
    html = _render(app, embed_videos=[
        {'url': 'https://www.youtube.com/embed/a', 'label': 'YouTube', 'embed': True}],
        videos=[{'url': 'https://www.youtube.com/embed/a', 'label': 'YouTube', 'embed': True}])
    assert '<iframe' in html and 'https://www.youtube.com/embed/a' in html


def test_template_does_not_embed_non_whitelist(app):
    html = _render(app, embed_videos=[
        {'url': 'https://evil.example.com/v.mp4', 'label': 'x', 'embed': True}],
        videos=[{'url': 'https://evil.example.com/v.mp4', 'label': 'x', 'embed': True}])
    import re
    for tag in re.findall(r'<iframe[^>]*>', html, re.I | re.S):
        assert 'evil.example.com' not in tag, f'非白名单被嵌入: {tag}'
    # 降级为外链
    assert 'evil.example.com' in html and '在新窗口打开' in html


@pytest.mark.parametrize('evil', [
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'https://evil.example.com/x" onload="alert(1)',
])
def test_template_rejects_evil_even_if_view_layer_is_bypassed(app, evil):
    """即使视图层被绕过（直接把恶意 URL 塞进 embed_videos），模板也必须挡住"""
    html = _render(app, embed_videos=[{'url': evil, 'label': 'x', 'embed': True}],
                   videos=[{'url': evil, 'label': 'x', 'embed': True}])
    import re
    low = html.lower()
    assert 'onload="alert(1)"' not in low
    for tag in re.findall(r'<iframe[^>]*>', html, re.I | re.S):
        assert 'javascript:' not in tag.lower()
        assert 'data:' not in tag.lower()
        assert 'evil.example.com' not in tag


def test_template_renders_with_no_videos(app):
    html = _render(app, videos=[], embed_videos=[], link_videos=[])
    assert '返回新闻列表' in html


def test_template_degrades_when_fetch_failed(app):
    html = _render(app, fetch_failed=True)
    assert '抓取失败' in html


# ===========================================================================
# 9) 上游抖动容错：历史语料不得被空结果覆盖（本轮修复的真实缺陷）
# ===========================================================================
@pytest.fixture
def clean_caches():
    anime_news._cache.clear()
    anime_news._translate_cache.clear()
    anime_news._corpus_fail_streak = 0
    yield
    anime_news._cache.clear()
    anime_news._translate_cache.clear()
    anime_news._corpus_fail_streak = 0


def test_upstream_failure_does_not_clobber_good_corpus(monkeypatch, clean_caches):
    """成功抓过一次后上游开始超时，列表/搜索仍应拿到旧语料而不是空"""
    goods = [{'title': 'A', 'link': 'https://a.example.com/1'}]

    class _Ok:
        def json(self):
            return {'data': goods}

    monkeypatch.setattr(anime_news.requests, 'get', lambda *a, **k: _Ok())
    monkeypatch.setattr(anime_news, '_translate_batch', lambda ts: {}, raising=False)
    assert anime_news._get_search_corpus() == goods

    # 上游开始持续失败
    def boom(*a, **k):
        raise anime_news.requests.exceptions.Timeout('read timed out')

    monkeypatch.setattr(anime_news.requests, 'get', boom)
    # 强制过期，迫使走回源路径
    anime_news._cache.pop(anime_news._CORPUS_KEY, None)

    assert anime_news._get_search_corpus() == goods, '历史语料被空结果覆盖了'
    assert anime_news._corpus_backoff_active(), '失败后应进入退避窗口'


def test_upstream_failure_with_no_history_returns_empty(monkeypatch, clean_caches):
    """从未成功过时，失败返回空并做短时负缓存（不能无限重试拖 12s 超时）"""
    def boom(*a, **k):
        raise anime_news.requests.exceptions.Timeout('read timed out')

    monkeypatch.setattr(anime_news.requests, 'get', boom)
    assert anime_news._get_search_corpus() == []
    assert anime_news._corpus_backoff_active()


def test_corpus_backoff_skips_upstream_call(monkeypatch, clean_caches):
    """退避窗口内不得再打上游（否则每个匿名请求都白等一次超时）"""
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise anime_news.requests.exceptions.Timeout('x')

    monkeypatch.setattr(anime_news.requests, 'get', boom)
    anime_news._get_search_corpus()
    assert len(calls) == 1
    anime_news._get_search_corpus()
    assert len(calls) == 1, f'退避窗口内又打了上游: {len(calls)} 次'


# ===========================================================================
# 10) 缓存上限：匿名换关键词不得刷爆实例内存
# ===========================================================================
def test_translate_cache_is_bounded():
    for i in range(anime_news._TRANSLATE_MAX + 500):
        anime_news._cache_set(anime_news._translate_cache, f'k{i}', f'v{i}',
                              anime_news._TRANSLATE_MAX)
    assert len(anime_news._translate_cache) <= anime_news._TRANSLATE_MAX
    anime_news._translate_cache.clear()


def test_search_cache_is_bounded(monkeypatch, clean_caches):
    """_cache 的键含用户可控搜索词，必须有上限"""
    monkeypatch.setattr(anime_news, '_get_search_corpus',
                        lambda: [{'title': 'tok', 'excerpt': ''}], raising=False)
    monkeypatch.setattr(anime_news, '_translate_keyword', lambda k: k, raising=False)
    for i in range(anime_news._CACHE_MAX + 300):
        anime_news.search_news(f'kw{i}')
    assert len(anime_news._cache) <= anime_news._CACHE_MAX


def test_prune_removes_expired_first():
    from datetime import datetime, timedelta
    cache = {}
    past = datetime.now() - timedelta(seconds=10)
    future = datetime.now() + timedelta(seconds=1000)
    for i in range(10):
        cache[f'old{i}'] = ('x', past)
    for i in range(10):
        cache[f'new{i}'] = ('y', future)
    anime_news._prune(cache, 10)
    assert len(cache) <= 10
    assert all(k.startswith('new') for k in cache), '未优先淘汰已过期条目'


def test_cache_accessors_are_thread_safe():
    """并发读改写不得抛 'dictionary changed size during iteration'"""
    errors = []
    anime_news._cache.clear()

    def writer(base):
        try:
            for i in range(400):
                anime_news._cache_set(anime_news._cache, f'w{base}-{i}',
                                      (i, time.time() + 100), 50)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    def reader():
        try:
            for _ in range(400):
                anime_news._cache_items(anime_news._cache)
                anime_news._cache_keys(anime_news._cache)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    anime_news._cache.clear()
    assert errors == [], f'并发下出错: {errors}'
