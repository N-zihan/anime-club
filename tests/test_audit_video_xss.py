"""T5 独立复检 · 番剧新闻视频抓取的对抗性测试（红队用例）

这些用例刻意以「攻击者视角」构造畸形/恶意 HTML，直接调用
app/anime_news.py 的正文解析入口，验证：
  1. 只有白名单域名的视频才能进入可嵌入结果；
  2. javascript: / data: 等伪协议一律被挡；
  3. 属性逃逸（" onload="alert(1)）不会污染返回的 URL 字段；
  4. 解析过程绝不会因为 HTML 里出现外链就去请求那个域（无任意域 SSRF）；
  5. 大写/畸形/未闭合标签不会绕过校验。

注意：这些测试以「最终修复后的接口」为准（result['videos']）。
若目标函数尚未实现 videos 字段，测试会明确 skip 而不是静默通过，
以便复检报告中区分「未实现」与「已实现且有漏洞」。

★ 本文件曾在 2026-10-17 21:16~21:51 之间被外部删除（只剩 .pyc），
  已由 T5 从审计记录完整重建。它是安全回归测试，请勿删除。
"""
import os

import pytest

from app import anime_news

# ---------------------------------------------------------------------------
# 构造一段一定能通过 len(full_text) > 100 与段落长度 > 20 的正文骨架
# ---------------------------------------------------------------------------
_FILLER = (
    '<p>This is a sufficiently long filler paragraph used to satisfy the '
    'minimum content length requirement of the article extractor.</p>'
    '<p>Another equally long filler paragraph so that translation and length '
    'checks both pass without any network access at all.</p>'
)

_VIDEO_HOSTS = ('youtube.com', 'www.youtube.com', 'youtu.be', 'player.bilibili.com',
                'www.bilibili.com', 'bilibili.com', 'player.vimeo.com', 'vimeo.com')


def _article(body):
    return f'<html><head><title>Audit Article</title></head><body><article>{_FILLER}{body}</article></body></html>'


@pytest.fixture
def parse(monkeypatch):
    """把网络与翻译全部替换为本地桩，只保留纯解析逻辑。

    返回 (result, requested_urls)：result 为解析结果，requested_urls 记录
    解析期间真实发起过的 HTTP 请求地址（用于 SSRF 断言）。
    """
    requested = []

    def fake_safe_get(url, **kwargs):
        requested.append(url)

        class _Res:
            status_code = 200
            text = _pending_html[0]

            def raise_for_status(self):
                return None

        return _Res()

    def fake_safe_get_no_network(url, **kwargs):
        # 任何一次真实外发请求都直接判定为 SSRF 隐患
        requested.append(url)
        raise AssertionError(f'解析过程发起了对外请求（SSRF 隐患）: {url!r}')

    _pending_html = ['']

    monkeypatch.setattr(anime_news, 'safe_get', fake_safe_get, raising=False)
    # 翻译一律原样返回，避免任何外网依赖
    monkeypatch.setattr(anime_news, '_translate_article', lambda text: text, raising=False)
    monkeypatch.setattr(anime_news, '_aliyun_call', lambda *a, **k: None, raising=False)
    # 清缓存，避免用例之间互相污染
    getattr(anime_news, '_article_cache', {}).clear()

    def _parse(body):
        _pending_html[0] = _article(body)
        result = anime_news.get_article_content('https://news.nanyi-anime-club.top/audit-case')
        assert result is not None, '解析结果不应为 None（正文骨架已满足长度要求）'
        return result

    _parse.requested = requested
    _parse.no_network = fake_safe_get_no_network
    yield _parse
    getattr(anime_news, '_article_cache', {}).clear()


def test_skeleton_is_not_a_noop(parse):
    """健全性自检：确认正文骨架真能走通解析，防止本文件全部用例「空转」。"""
    result = parse('<iframe src="https://www.youtube.com/embed/a"></iframe>')
    assert set(result) >= {'content', 'images', 'title'}, f'返回字段异常: {sorted(result)}'
    assert len(result['content']) >= 100, '正文长度不足，用例可能是空转的'
    assert parse.requested == ['https://news.nanyi-anime-club.top/audit-case'], \
        f'除文章自身外不应有其它请求: {parse.requested}'


def _videos(result):
    """取出视频结果；未实现 videos 字段时明确 skip。"""
    if 'videos' not in result:
        pytest.skip("get_article_content 未返回 'videos' 字段（T3 尚未实现视频提取）")
    videos = result['videos']
    assert isinstance(videos, (list, tuple)), f'videos 应为序列，实际 {type(videos)!r}'
    return videos


def _flat(videos):
    """把 videos 展开为便于断言的 (kind, url) 列表，兼容 dict/str 元素。"""
    out = []
    for v in videos:
        if isinstance(v, str):
            out.append(('unknown', v))
        elif isinstance(v, dict):
            url = v.get('url') or v.get('src') or ''
            out.append((v.get('type') or v.get('kind') or 'unknown', url or ''))
        else:
            out.append(('unknown', str(v)))
    return out


# ===========================================================================
# 1) 白名单 iframe：应当被提取
# ===========================================================================
@pytest.mark.parametrize('src', [
    'https://www.youtube.com/embed/dQw4w9WgXcQ',
    'https://player.bilibili.com/player.html?bvid=BV1xx411c7mD',
    'https://player.vimeo.com/video/123456789',
])
def test_whitelist_iframe_is_extracted(parse, src):
    result = parse(f'<iframe src="{src}" width="560" height="315"></iframe>')
    urls = [u for _, u in _flat(_videos(result))]
    assert any(src in u for u in urls), f'白名单 iframe 未被提取: {src} → {urls}'


# ===========================================================================
# 2) 非白名单 iframe：绝不能作为可嵌入视频出现
# ===========================================================================
@pytest.mark.parametrize('src', [
    'https://evil.example.com/embed/x',
    'https://attacker.test/xss.html',
    'https://news.nanyi-anime-club.top/self.html',
    'https://youtube.com.evil.test/embed/x',
    'https://evil-youtube.com/embed/x',
    'https://notyoutube.com/embed/x',
    # --- 主机名混淆族：必须全部被拒 ---
    'https://www.youtube.com@evil.example.com/embed/x',
    'https://evil.example.com#@www.youtube.com/embed/x',
    'https://www.youtube.com.evil.example.com/embed/x',
    'https://www.youtube.com%00.evil.example.com/embed/x',
    'https://www.youtube.com%2F@evil.example.com/embed/x',
    'https://xn--youtube-xxx.com/embed/x',
    'https://www.youtube.com:evil.example.com/embed/x',
    'https://evil.example.com/www.youtube.com/embed/x',
    'https://www.youtube.com.evil.example.com:443/embed/x',
])
def test_non_whitelist_iframe_is_not_embeddable(parse, src):
    result = parse(f'<iframe src="{src}"></iframe>')
    videos = _videos(result)
    for kind, url in _flat(videos):
        assert url != src, f'非白名单 iframe 进入了视频列表: {src}'
        if kind in ('iframe', 'embed'):
            host = url.split('/')[2] if '//' in url else url
            assert any(h in host for h in _VIDEO_HOSTS), \
                f'非白名单地址被标记为可嵌入 iframe: {url}'
    # 任何被判为可嵌入(embed=True)的项，host 必须真的是白名单域
    for v in videos:
        if isinstance(v, dict) and v.get('embed'):
            u = v.get('url') or ''
            host = u.split('/')[2].split('@')[-1].split(':')[0].lower() if '//' in u else ''
            assert any(host == h or host.endswith('.' + h) for h in _VIDEO_HOSTS), \
                f'embed=True 但 host 不在白名单: {u!r}'


@pytest.mark.parametrize('src,should_allow', [
    # 大小写不敏感：应放行
    ('https://WWW.YOUTUBE.COM/embed/a', True),
    ('https://Player.BiliBili.com/player.html?bvid=BV1', True),
    # 尾点：DNS 语义上等价于白名单域，允许与否都可接受，但绝不能被当成非白名单 embed
    ('https://www.youtube.com./embed/a', None),
    # 显式端口：允许
    ('https://www.youtube.com:443/embed/a', True),
])
def test_host_case_and_trailing_dot(parse, src, should_allow):
    """大小写/尾点/显式端口不得绕过白名单判定，也不得把非白名单放进来。"""
    result = parse(f'<iframe src="{src}"></iframe>')
    embeds = [v for v in _videos(result) if isinstance(v, dict) and v.get('embed')]
    if should_allow is True:
        assert embeds, f'合法白名单变体被误拒: {src}'
    for v in embeds:
        host = v['url'].split('/')[2].split('@')[-1].split(':')[0].lower().strip('.')
        assert any(host == h or host.endswith('.' + h) for h in _VIDEO_HOSTS), \
            f'embed=True 的 host 不在白名单: {v["url"]!r}'


# ---------------------------------------------------------------------------
# 2b) netloc 花招族：userinfo 伪装 / 反向伪装 / 边界端口 / 片段混淆
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('src,expect_embed', [
    # userinfo 伪装：实际连到 evil.example.com → 必须拒绝
    ('https://www.youtube.com@evil.example.com/embed/x', False),
    # 反向伪装：userinfo 是 evil，实际连到 www.youtube.com。
    # 保守拒绝（因 username 非空）与放行都可接受；关键是绝不能错标成非白名单域。
    ('https://evil.example.com@www.youtube.com/embed/x', None),
    # 合法显式端口必须放行（防止修过头误杀）
    ('https://www.youtube.com:443/embed/x', True),
    # 边界端口：0 与越界端口都不是有效连接目标 → 必须拒绝
    ('https://www.youtube.com:0/embed/x', False),
    ('https://www.youtube.com:99999/embed/x', False),
    # 非数字端口 → 必须拒绝
    ('https://www.youtube.com:evil.example.com/embed/x', False),
    # 片段混淆
    ('https://www.youtube.com#@evil.example.com', False),
    # 子串匹配绕过
    ('https://notyoutube.com.evil.test/embed', False),
    ('https://youtube.com.evil.test/embed', False),
    # 大写域名（合法变体）必须放行
    ('https://WWW.YOUTUBE.COM/embed/x', True),
])
def test_netloc_tricks(parse, src, expect_embed):
    """netloc 花招必须被正确处理；同时合法变体不得被误杀。"""
    result = parse(f'<iframe src="{src}"></iframe>')
    embeds = [v for v in _videos(result) if isinstance(v, dict) and v.get('embed')]

    # 任一 embed=True 的项，host 必须真的是白名单域（且不是 userinfo 伪装）
    for v in embeds:
        from urllib.parse import urlsplit as _us
        p = _us(v['url'])
        assert p.username is None, f'embed=True 但 URL 带 userinfo: {v["url"]!r}'
        host = (p.hostname or '').lower().strip('.')
        assert any(host == h or host.endswith('.' + h) for h in _VIDEO_HOSTS), \
            f'embed=True 但 host 不在白名单: {v["url"]!r} (host={host!r})'
        # 端口必须是合法整数
        try:
            p.port
        except ValueError:
            pytest.fail(f'embed=True 但端口非法: {v["url"]!r}')

    if expect_embed is True:
        assert embeds, f'合法嵌入被误拒（修过头回归）: {src}'
    elif expect_embed is False:
        assert not embeds, f'非法地址被误判为可嵌入: {src} → {embeds}'


# ---------------------------------------------------------------------------
# 2c) 关键回归：真实嵌入 URL（带查询串与 &）绝不能被误杀
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('src', [
    'https://www.youtube.com/embed/dQw4w9WgXcQ?si=abc123&t=30',
    'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0',
    'https://player.bilibili.com/player.html?bvid=BV1xx411c7mD&page=1&high_quality=1',
    'https://player.vimeo.com/video/123456789?h=abc123&title=0',
    'https://www.youtube.com/embed/a',
])
def test_real_embeds_not_over_rejected(parse, src):
    """「别修过头」守卫：真实白名单嵌入 URL（含查询串 &）必须仍被识别为可嵌入。

    若净化逻辑为了拒绝危险字符而连 `?` `&` `=` 都拒，正常视频会全部失效——
    这是功能性回归，必须报出来。
    """
    result = parse(f'<iframe src="{src}" width="560" height="315"></iframe>')
    embeds = [v for v in _videos(result) if isinstance(v, dict) and v.get('embed')]
    assert embeds, f'真实嵌入 URL 被误杀（功能性回归）: {src}'
    # 查询串必须保留，否则播放器参数（起始时间等）会丢失
    if '?' in src:
        assert any('?' in v['url'] for v in embeds), \
            f'查询串被剥掉，播放器参数丢失: {[v["url"] for v in embeds]}'


# ===========================================================================
# 3) javascript: / data: / vbscript: 伪协议
# ===========================================================================
@pytest.mark.parametrize('src', [
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==',
    'vbscript:msgbox(1)',
    'file:///etc/passwd',
    '//evil.example.com/x',
    'blob:https://evil.example.com/uuid',
])
def test_pseudo_protocol_is_blocked(parse, src):
    result = parse(f'<iframe src="{src}"></iframe>')
    for kind, url in _flat(_videos(result)):
        lowered = url.strip().lower()
        assert not lowered.startswith(('javascript:', 'data:', 'vbscript:', 'file:', 'blob:')), \
            f'伪协议未被过滤: {url!r}'
        assert not lowered.startswith('//'), f'协议相对地址未被过滤: {url!r}'


# ===========================================================================
# 4) 属性逃逸：引号打断属性 + onload 事件
# ===========================================================================
@pytest.mark.parametrize('body', [
    '<iframe src="https://evil.example.com/x" onload="alert(1)"></iframe>',
    '<iframe src=https://evil.example.com/x onload=alert(1)></iframe>',
    '<iframe src="javascript:alert(1)" onload="alert(2)"></iframe>',
    '<iframe src="https://www.youtube.com/embed/a" onload="alert(1)"></iframe>',
    '<iframe src="https://www.youtube.com/embed/a&amp;quot; onload=&amp;quot;alert(1)"></iframe>',
    '<video src="x" onerror="alert(1)"><source src="y" onerror="alert(2)"></video>',
])
def test_event_handler_does_not_leak_into_result(parse, body):
    """解析层不得产出含「真实逃逸原语」的 URL。

    T5 裁定的断言边界（有实测依据，见 reports/T5-复检报告.md）：
      · raw " 或 ' → **真实逃逸原语**。实测：src 值里的 raw 引号一旦被 |safe
        渲染，会派生可执行的 onload 属性；模板换成单引号包裹也挡不住另一种引号。
        ⇒ 解析层必须拒绝含 raw 引号的 URL（纵深防御，不能把安全性全押在模板转义上）。
      · `&quot;` 实体残留 → **不可利用**。HTML 字符引用在属性值定界之后才解码，
        不会 re-tokenize；实测任何包裹方式都不会凭空多出 onload。
        ⇒ 不应断言结果里「不含 onload 子串」，那是过严且理由不成立的断言。
    """
    result = parse(body)
    for kind, url in _flat(_videos(result)):
        for ch, name in (('"', '双引号'), ("'", '单引号'), ('<', '左尖括号'),
                         ('>', '右尖括号'), ('`', '反引号')):
            assert ch not in url, f'URL 字段含真实逃逸原语({name}): {url!r}'
        for ws in (' ', '\t', '\n', '\r', '\x00'):
            assert ws not in url, f'URL 字段含空白/控制字符({ws!r}): {url!r}'


@pytest.mark.parametrize('body', [
    # 单引号属性包裹 + raw 双引号：raw 引号确实能存活进 src 值（真实原语）
    """<iframe src='https://www.youtube.com/embed/a"onload="alert(1)'></iframe>""",
    # 无引号属性 + raw 双引号：同样存活
    '<iframe src=https://www.youtube.com/embed/a"onload="alert(1)></iframe>',
    # 单引号属性包裹 + raw 单引号
    """<iframe src='https://www.youtube.com/embed/a'onload='alert(1)'></iframe>""",
])
def test_raw_quote_primitive_never_survives(parse, body):
    """专项回归：raw 引号是真实逃逸原语，必须在解析层被清除/拒绝。"""
    result = parse(body)
    for kind, url in _flat(_videos(result)):
        assert '"' not in url, f'raw 双引号存活进 URL（真实逃逸原语）: {url!r}'
        assert "'" not in url, f'raw 单引号存活进 URL（真实逃逸原语）: {url!r}'


# ---------------------------------------------------------------------------
# 4b) 编码绕过族：单层实体 / 双重实体 / 单层与双重百分号编码 / NUL 字节
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('body', [
    # 单层实体（&quot; 本身就是实体写法）
    '<iframe src="https://www.youtube.com/embed/a&quot;onload=&quot;alert(1)"></iframe>',
    # 双重实体：&amp;amp;quot; 解码一层后剩 &amp;quot;，再解码一层才成 &quot;
    '<iframe src="https://www.youtube.com/embed/a&amp;amp;quot;onload=&amp;amp;quot;alert(1)"></iframe>',
    # 单层百分号编码
    '<iframe src="https://www.youtube.com/embed/a%22onload=%22alert(1)"></iframe>',
    # 双重百分号编码
    '<iframe src="https://www.youtube.com/embed/a%2522onload=%2522alert(1)"></iframe>',
    # %3C / %3E 尖括号
    '<iframe src="https://www.youtube.com/embed/a%3Cscript%3E"></iframe>',
    # NUL 字节：单层与百分号编码两种写法
    '<iframe src="https://www.youtube.com/embed/a%00b"></iframe>',
    '<iframe src="https://www.youtube.com/embed/a\x00b"></iframe>',
    # 实体化的尖括号 + onload
    '<iframe src="https://www.youtube.com/embed/a&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>',
])
def test_encoding_bypass_family(parse, body):
    """任何编码层次的绕过，最终返回的 URL 都不得含可执行原语。"""
    result = parse(body)
    for kind, url in _flat(_videos(result)):
        low = url.lower()
        assert '"' not in url, f'编码绕过后出现 raw 双引号: {url!r}'
        assert "'" not in url, f'编码绕过后出现 raw 单引号: {url!r}'
        assert '<' not in url and '>' not in url, f'编码绕过后出现尖括号: {url!r}'
        assert '\x00' not in url, f'URL 含 NUL 字节: {url!r}'
        assert '\n' not in url and '\r' not in url and '\t' not in url, \
            f'URL 含控制字符: {url!r}'
        assert not low.startswith(('javascript:', 'data:', 'vbscript:', 'file:', 'blob:')), \
            f'编码绕过后出现伪协议: {url!r}'


@pytest.mark.parametrize('body', [
    '<iframe src="https://www.youtube.com/embed/a&amp;quot; onload=&amp;quot;alert(1)"></iframe>',
    '<iframe src="https://www.youtube.com/embed/a&quot;onload=&quot;alert(1)"></iframe>',
    '<iframe src="https://www.youtube.com/embed/a"onload="alert(1)"></iframe>',
    """<iframe src='https://www.youtube.com/embed/a"onload="alert(1)'></iframe>""",
])
def test_root_cause_not_patched_by_truncation(parse, body):
    """根因断言：不得靠「把 URL 截断到刚好不含 onload」这种碰巧过关。

    要求：对白名单域的视频，要么**完全拒绝**（不出现在 videos 里），
    要么产出一个**干净、完整、可用的** YouTube embed URL——
    而不是一个被截断的残URL（残URL 既无功能价值，又说明只做了字符串修剪）。
    """
    result = parse(body)
    for kind, url in _flat(_videos(result)):
        low = url.lower()
        # 不得残留任何事件处理器片段或实体残渣
        assert 'onload' not in low, f'URL 残留事件处理器片段（未清根因）: {url!r}'
        assert 'alert' not in low, f'URL 残留注入载荷（未清根因）: {url!r}'
        assert '&quot' not in low and '&amp' not in low, \
            f'URL 残留 HTML 实体残渣: {url!r}'
        # 若保留了白名单视频，必须是完整可用的 embed 形态
        if 'youtube.com' in low:
            assert '/embed/' in low, f'白名单 URL 被截断成残URL: {url!r}'
            vid = low.split('/embed/', 1)[1]
            assert vid and vid.strip() == vid, f'视频 ID 被截断/含杂质: {url!r}'
            assert all(c.isalnum() or c in '-_' for c in vid), \
                f'视频 ID 含非法字符，说明未做字符级净化: {url!r}'


# ===========================================================================
# 5) 大写 / 畸形 / 未闭合标签
# ===========================================================================
@pytest.mark.parametrize('body,expect_youtube', [
    ('<IFRAME SRC="https://www.youtube.com/embed/a"></IFRAME>', True),
    ('<iframe  src = "https://www.youtube.com/embed/a" >', False),
    ('<IfRaMe SrC="javascript:alert(1)"></IfRaMe>', False),
    ('<iframe src="https://evil.example.com/x">', False),
    ('<iframe src="https://www.youtube.com/embed/a"', False),
])
def test_malformed_tags(parse, body, expect_youtube):
    result = parse(body)
    urls = ' '.join(u for _, u in _flat(_videos(result))).lower()
    assert 'javascript:' not in urls, f'畸形标签绕过了伪协议过滤: {urls}'
    if expect_youtube and 'videos' in result:
        assert 'youtube.com' in urls, f'合法大写标签未被识别: {body}'


# ===========================================================================
# 6) <video> / <source>
# ===========================================================================
def test_video_and_source_extracted(parse):
    body = ('<video controls poster="https://cdn.example.com/p.jpg">'
            '<source src="https://cdn.example.com/movie.mp4" type="video/mp4">'
            '</video>')
    result = parse(body)
    urls = ' '.join(u for _, u in _flat(_videos(result)))
    assert 'movie.mp4' in urls, f'<source src> 未被提取: {urls}'


def test_video_js_src_blocked(parse):
    body = '<video controls><source src="javascript:alert(1)"></video>'
    result = parse(body)
    for _, url in _flat(_videos(result)):
        assert not url.strip().lower().startswith('javascript:'), f'<source> 伪协议未过滤: {url!r}'


# ===========================================================================
# 7) og:video / twitter:player meta
# ===========================================================================
@pytest.mark.parametrize('prop', ['og:video', 'og:video:url', 'og:video:secure_url', 'twitter:player'])
@pytest.mark.parametrize('src', [
    'https://www.youtube.com/embed/a',
    'https://player.bilibili.com/player.html?bvid=BV1',
    'https://evil.example.com/v.mp4',
    'javascript:alert(1)',
])
def test_meta_video_handling(parse, prop, src):
    body = f'<meta property="{prop}" content="{src}">'
    result = parse(body)
    for _, url in _flat(_videos(result)):
        lowered = url.strip().lower()
        assert not lowered.startswith(('javascript:', 'data:', 'vbscript:')), \
            f'meta 中的伪协议未被过滤 ({prop}): {url!r}'
        if 'evil.example.com' in lowered and prop.startswith('og:video'):
            # og:video 若作为「外链」返回可以接受，但不能被当成可嵌入 iframe
            assert '/embed/' not in lowered or 'www.youtube.com' in lowered, \
                f'任意域被当成可嵌入视频: {url!r}'


# ===========================================================================
# 8) SSRF：HTML 中出现外链不得触发解析期请求
# ===========================================================================
def test_no_arbitrary_ssrf_during_parse(parse):
    body = ('<iframe src="https://www.youtube.com/embed/a"></iframe>'
            '<iframe src="https://attacker.example.com/probe"></iframe>'
            '<video><source src="https://internal.corp.local/secret.mp4"></video>'
            '<img src="http://169.254.169.254/latest/meta-data/">')
    parse(body)
    # 只允许对文章自身 URL 发起一次请求
    external = [u for u in parse.requested if u != 'https://news.nanyi-anime-club.top/audit-case']
    assert external == [], f'解析过程对外发起了额外请求: {external}'


# ===========================================================================
# 9) 模板层：不得对视频 URL 直接使用 |safe 且必须做白名单判断
# ===========================================================================
def test_detail_template_does_not_raw_output_video_url():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'templates', 'anime_news_detail.html')
    if not os.path.exists(path):
        pytest.skip('templates/anime_news_detail.html 不存在')
    with open(path, encoding='utf-8') as fh:
        src = fh.read()
    # 粗筛：iframe src 直接绑定变量且带 |safe
    import re as _re
    for m in _re.finditer(r'<iframe[^>]*>', src, _re.I | _re.S):
        tag = m.group(0)
        if '|safe' in tag:
            pytest.fail(f'iframe 标签内出现 |safe，存在 XSS 风险: {tag!r}')
