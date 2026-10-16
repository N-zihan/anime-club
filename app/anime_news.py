"""
动漫社官网 · 动漫新闻数据源
====================================
从自部署的 AniNewsAPI 聚合动漫新闻，使用阿里云机器翻译。
"""
import base64
import hashlib
import hmac
import json
import os
import re
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .utils import safe_get

ANI_NEWS_API = 'https://news.nanyi-anime-club.top/'

_cache = {}
_CACHE_TTL = 1800

_translate_cache = {}  # 翻译缓存（永久，进程重启后清空）

_article_cache = {}
_ARTICLE_TTL = 172800

_UA = 'Mozilla/5.0 (compatible; nanyi-anime-club/1.0)'

# 阿里云机器翻译端点
_ALIYUN_MT_ENDPOINT = 'https://mt.aliyuncs.com/'
_ALIYUN_SINGLE_MAX = 4500  # 单次请求最大字符数（保守取值）


# ============================================================
# 阿里云翻译
# ============================================================
def _aliyun_call(text, source='en', target='zh'):
    """单次调用阿里云机器翻译 API，返回翻译文本（失败返回 None）"""
    if not text or not text.strip():
        return ''

    ak_id = os.getenv('ALIBABA_CLOUD_ACCESS_KEY_ID')
    ak_secret = os.getenv('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
    if not ak_id or not ak_secret:
        return None

    params = {
        'Action': 'TranslateGeneral',
        'Version': '2018-10-12',
        'Format': 'JSON',
        'AccessKeyId': ak_id,
        'SignatureMethod': 'HMAC-SHA1',
        'SignatureVersion': '1.0',
        'SignatureNonce': str(uuid.uuid4()),
        'Timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'FormatType': 'text',
        'SourceLanguage': source,
        'TargetLanguage': target,
        'SourceText': text,
        'Scene': 'general',
    }

    # 阿里云签名算法
    sorted_params = sorted(params.items())
    canonicalized = '&'.join(
        f'{quote(k, safe="")}={quote(str(v), safe="")}'
        for k, v in sorted_params
    )
    string_to_sign = 'GET&%2F&' + quote(canonicalized, safe='')
    signature = base64.b64encode(
        hmac.new(
            (ak_secret + '&').encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1,
        ).digest()
    ).decode('utf-8')

    params['Signature'] = signature

    try:
        res = requests.get(_ALIYUN_MT_ENDPOINT, params=params, timeout=8)
        data = res.json()
        if data.get('Code') == '200':
            return data.get('Data', {}).get('Translated', '')
        print(f'>>> 阿里云翻译错误: code={data.get("Code")} msg={data.get("Message")}')
        return None
    except Exception as e:
        print(f'>>> 阿里云请求失败: {e}')
        return None


def _translate_batch(texts):
    """批量翻译（英→中），带缓存。
    texts: list[str]，返回 {原文: 译文}。
    """
    if not texts:
        return {}

    result = {}
    to_translate = []

    for t in texts:
        if not t or not t.strip():
            result[t] = t
            continue
        cached = _translate_cache.get(t)
        if cached:
            result[t] = cached
        else:
            to_translate.append(t)

    if not to_translate:
        return result

    # 阿里云没有原生批量接口，用 \n 拼接实现伪批量
    # 按字符数分批，防止单次请求超长
    batches = []
    current = []
    current_len = 0

    for t in to_translate:
        # 单条太长，单独处理
        if len(t) > _ALIYUN_SINGLE_MAX:
            if current:
                batches.append(current)
                current = []
                current_len = 0
            batches.append([t])
            continue

        if current_len + len(t) + 1 > _ALIYUN_SINGLE_MAX:
            batches.append(current)
            current = [t]
            current_len = len(t)
        else:
            current.append(t)
            current_len += len(t) + 1

    if current:
        batches.append(current)

    def _run_batch(batch):
        """翻译单个批次，返回 {原文: 译文}"""
        out = {}
        # 单条超长的情况，直接单独调用
        if len(batch) == 1 and len(batch[0]) > _ALIYUN_SINGLE_MAX:
            # 截断处理（超过 4500 字符的文本很少见）
            truncated = batch[0][:_ALIYUN_SINGLE_MAX]
            translated = _aliyun_call(truncated)
            if translated:
                out[batch[0]] = translated
                _translate_cache[batch[0]] = translated
            else:
                out[batch[0]] = batch[0]
            return out

        joined = '\n'.join(batch)
        translated = _aliyun_call(joined)

        if translated is None:
            # 调用失败，原样返回
            for t in batch:
                out[t] = t
            return out

        lines = translated.split('\n')

        # 行数不匹配时，降级为逐条翻译
        if len(lines) != len(batch):
            print(f'>>> 行数不匹配（{len(lines)} vs {len(batch)}），降级逐条翻译')
            for t in batch:
                single = _aliyun_call(t)
                zh = single if single else t
                out[t] = zh
                _translate_cache[t] = zh
            return out

        for orig, trans in zip(batch, lines):
            zh = trans.strip() or orig
            out[orig] = zh
            _translate_cache[orig] = zh
        return out

    # 并发翻译各批次：原先串行执行，20 条新闻冷启动可累计 30 秒以上
    with ThreadPoolExecutor(max_workers=min(4, len(batches))) as pool:
        for partial in pool.map(_run_batch, batches):
            result.update(partial)

    return result


# ============================================================
# 新闻列表
# ============================================================
def _decode_cursor(cursor):
    """AniNews 游标是 base64(JSON)，解析出 offset；失败返回 None"""
    try:
        padded = cursor + '=' * (-len(cursor) % 4)
        return json.loads(base64.b64decode(padded).decode('utf-8')).get('offset')
    except Exception:
        return None


def _encode_cursor(offset):
    """生成与上游格式兼容的 base64(JSON) 游标"""
    payload = json.dumps({'offset': int(offset)}, separators=(',', ':'))
    return base64.b64encode(payload.encode('utf-8')).decode('utf-8')


# 搜索语料：预取一次全量新闻（当前约百条）并只翻译标题，6 小时内供列表与搜索复用
_CORPUS_KEY = 'corpus_search'
_CORPUS_TTL = 21600


def _get_search_corpus():
    """获取搜索语料（标题已译）。空语料做短时负缓存，避免上游抖动时反复超时"""
    now = datetime.now()
    entry = _cache.get(_CORPUS_KEY)
    if entry:
        arts, expires = entry
        if now < expires:
            if arts:
                # 顺带回填已缓存的摘要翻译
                for a in arts:
                    e = a.get('excerpt') or ''
                    if e and not a.get('excerpt_zh') and _translate_cache.get(e):
                        a['excerpt_zh'] = _translate_cache[e]
            return arts

    try:
        res = requests.get(f'{ANI_NEWS_API}/api/news', params={'limit': 100}, timeout=12)
        data = res.json()
        arts = data.get('data') if isinstance(data, dict) else None
        if not isinstance(arts, list):
            return []
        arts = [a for a in arts if isinstance(a, dict)]

        # 只批量翻译标题：摘要不额外翻译，控制冷启动耗时
        titles = [a.get('title') for a in arts if a.get('title')]
        if titles:
            zh = _translate_batch(titles)
            for a in arts:
                if a.get('title'):
                    a['title_zh'] = zh.get(a['title'], a['title'])

        if arts:
            _cache[_CORPUS_KEY] = (arts, now + timedelta(seconds=_CORPUS_TTL))
        return arts
    except Exception as e:
        print(f'>>> 搜索语料拉取失败: {e}')
        # 负缓存 60 秒：防止上游抖动时每个请求都拖一次 12 秒超时
        _cache[_CORPUS_KEY] = ([], now + timedelta(seconds=60))
        return []


def find_article_meta(url):
    """按链接查找文章元数据：先查搜索语料，再回退已缓存列表；找不到返回 None"""
    if not url:
        return None
    for a in _get_search_corpus():
        if (a.get('link') or a.get('url')) == url:
            return a
    cache_keys = [k for k in _cache if str(k).startswith('news_')]
    if cache_keys:
        latest_key = max(cache_keys, key=lambda k: _cache[k][1])
        cached_articles = _cache[latest_key][0]
        arts = cached_articles[0] if isinstance(cached_articles, tuple) else cached_articles
        for a in arts:
            if (a.get('link') or a.get('url')) == url:
                return a
    return None


def get_anime_news(limit=20, tag=None, cursor=None):
    """获取动漫新闻列表，返回 (articles, meta)"""
    cache_key = f'news_{limit}_{tag or "all"}_{cursor or "start"}'
    now = datetime.now()

    if cache_key in _cache:
        data, expires = _cache[cache_key]
        if now < expires:
            return data

    # 无 tag 且游标可解析时，直接从本地语料切片返回：
    # 避免冷启动串行等待上游抓取 + 逐批翻译
    if not tag:
        offset = _decode_cursor(cursor) if cursor else 0
        if offset is not None and offset >= 0:
            corpus = _get_search_corpus()
            if corpus:
                page = corpus[offset:offset + limit]
                has_more = offset + limit < len(corpus)
                next_cursor = _encode_cursor(offset + limit) if has_more else None
                result = (page, {'total': len(corpus), 'hasMore': has_more,
                                 'nextCursor': next_cursor})
                _cache[cache_key] = (result, now + timedelta(seconds=_CACHE_TTL))
                return result

    params = {'limit': limit}
    if tag:
        params['tag'] = tag
    if cursor:
        params['cursor'] = cursor

    url = f'{ANI_NEWS_API}/api/news'
    print(f'>>> 请求 AniNews: {url} params={params}')

    try:
        res = requests.get(url, params=params, timeout=15)
        print(f'>>> HTTP 状态: {res.status_code}')

        data = res.json()

        articles = []
        meta = {}
        if isinstance(data, dict):
            articles = data.get('data') or data.get('articles') or []
            meta = data.get('meta') or {}
        elif isinstance(data, list):
            articles = data

        # ★ 标题 + 摘要一次批量翻译
        if articles:
            all_texts = []
            for a in articles:
                if a.get('title'):
                    all_texts.append(a['title'])
                if a.get('excerpt'):
                    all_texts.append(a['excerpt'])

            if all_texts:
                translated = _translate_batch(all_texts)
                for a in articles:
                    t = a.get('title', '')
                    e = a.get('excerpt', '')
                    if t:
                        a['title_zh'] = translated.get(t, t)
                    if e:
                        a['excerpt_zh'] = translated.get(e, e)

        result = (articles, meta)
        _cache[cache_key] = (result, now + timedelta(seconds=_CACHE_TTL))
        return result

    except Exception as e:
        print(f'>>> AniNews 请求失败: {e}')
        traceback.print_exc()
        return [], {}


# ============================================================
# 搜索
# ============================================================
def search_news(keyword, limit=50):
    """搜索新闻。中文关键词会先翻译成英文再匹配。"""
    if not keyword:
        return []

    keyword = keyword.strip()
    if not keyword:
        return []

    # 搜索缓存键
    cache_key = f'search:{keyword.lower()}:{limit}'
    now = datetime.now()
    if cache_key in _cache:
        cached_data, expires = _cache[cache_key]
        if now < expires:
            return cached_data

    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in keyword)

    # 语料拉取与关键词翻译并行执行：原实现三段串行
    # （列表抓取→批量翻译→关键词翻译），冷启动最坏可累计 30 秒以上
    kw_future = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        corpus_future = pool.submit(_get_search_corpus)
        if has_chinese:
            kw_future = pool.submit(_translate_keyword, keyword)
        articles = corpus_future.result()

    # 语料不可用时回退已缓存的列表数据
    if not articles:
        cache_keys = [k for k in _cache if k.startswith('news_')]
        if cache_keys:
            latest_key = max(cache_keys, key=lambda k: _cache[k][1])  # 按过期时间排序
            cached_articles, _ = _cache[latest_key]
            if isinstance(cached_articles, tuple):
                articles = cached_articles[0]  # 格式：(articles, meta)
            else:
                articles = cached_articles

    keywords = [keyword.lower()]

    # 关键词翻译已在语料拉取时并行执行，这里只取结果
    if kw_future is not None:
        try:
            translated = kw_future.result()
            if translated and translated.lower() != keyword.lower():
                keywords.append(translated.lower())
                print(f'>>> 搜索词翻译: "{keyword}" → "{translated}"')
        except Exception as e:
            print(f'>>> 搜索词翻译失败: {e}')
            # 翻译失败时仅使用原关键词搜索

    results = []
    for a in articles:
        title = (a.get('title') or '').lower()
        title_zh = (a.get('title_zh') or '').lower()
        excerpt = (a.get('excerpt') or '').lower()
        excerpt_zh = (a.get('excerpt_zh') or '').lower()
        tags = ' '.join(a.get('tags') or []).lower()

        haystack = ' '.join([title, title_zh, excerpt, excerpt_zh, tags])
        if any(kw in haystack for kw in keywords):
            results.append(a)
            if len(results) >= limit:
                break

    # 不缓存空结果：避免首次搜索无数据后，后续相同关键词也永远返回空
    if not results:
        return []

    # 缓存搜索结果 (5分钟)
    _cache[cache_key] = (results, now + timedelta(minutes=5))
    
    return results


def _translate_keyword(keyword):
    """把搜索关键词翻译成英文"""
    cache_key = 'KW:' + keyword
    if cache_key in _translate_cache:
        return _translate_cache[cache_key]

    translated = _aliyun_call(keyword, source='zh', target='en')
    if translated:
        translated = translated.strip().strip('"\'')
        _translate_cache[cache_key] = translated
        return translated
    return keyword


# ============================================================
# 新闻正文
# ============================================================
def get_article_content(url):
    """抓取原文章正文并翻译成中文"""
    if not url:
        return None

    now = datetime.now()
    if url in _article_cache:
        data, expires = _article_cache[url]
        if now < expires:
            return data

    try:
        res = safe_get(url, headers={'User-Agent': _UA}, timeout=15)
        if res is None:
            print('>>> 抓取原文被拦截（非公网地址或重定向过多）')
            return None
        res.raise_for_status()
    except Exception as e:
        print(f'>>> 抓取原文失败: {e}')
        return None

    try:
        soup = BeautifulSoup(res.text, 'html.parser')

        for tag in soup(['script', 'style', 'nav', 'header', 'footer',
                         'aside', 'form', 'iframe', 'noscript', 'button']):
            tag.decompose()

        article = (
            soup.find('article') or
            soup.find('main') or
            soup.find('div', class_=re.compile(r'(article|content|post|entry)', re.I)) or
            soup.body
        )

        if not article:
            return None

        paragraphs = []
        for p in article.find_all(['p', 'h2', 'h3']):
            text = p.get_text(' ', strip=True)
            if text and len(text) > 20:
                paragraphs.append(text)

        seen = set()
        cleaned = []
        for p in paragraphs:
            if p not in seen:
                seen.add(p)
                cleaned.append(p)

        full_text = '\n\n'.join(cleaned[:40])

        if len(full_text) < 100:
            return None

        # 翻译正文
        translated = _translate_article(full_text)

        # 提取文章中所有 https 图片链接
        images = []
        for img in article.find_all('img'):
            src = img.get('src')
            if not src:
                continue
            # 转为绝对地址
            import urllib.parse
            abs_url = urllib.parse.urljoin(url, src)
            if abs_url.startswith('https://'):
                images.append(abs_url)
        # 去重并限制数量
        seen = set()
        images = [u for u in images if u not in seen and not seen.add(u)][:8]
        
        result = {
            'title': soup.title.string.strip() if soup.title and soup.title.string else '',
            'content': translated,
            'images': images,
        }
        _article_cache[url] = (result, now + timedelta(seconds=_ARTICLE_TTL))
        return result

    except Exception as e:
        print(f'>>> 解析原文失败: {e}')
        traceback.print_exc()
        return None


def _translate_article(text):
    """翻译整篇文章。按段落分批调用阿里云，各批次并发执行。"""
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    if not paragraphs:
        return text

    BATCH_SIZE = 5  # 每批 5 段

    def _run_batch(batch):
        """翻译一批段落，返回译文片段列表"""
        joined = '\n'.join(batch)

        # 超过单次限制的批次拆成单段处理
        if len(joined) > _ALIYUN_SINGLE_MAX:
            parts = []
            for p in batch:
                if len(p) > _ALIYUN_SINGLE_MAX:
                    p = p[:_ALIYUN_SINGLE_MAX]
                single = _aliyun_call(p)
                parts.append(single if single else p)
            return parts

        translated = _aliyun_call(joined)
        if translated:
            return [translated]
        return ['\n'.join(batch)]

    jobs = [paragraphs[i:i + BATCH_SIZE]
            for i in range(0, len(paragraphs), BATCH_SIZE)]

    # 各批次并发翻译：原先串行执行，长文每多一批就多等一次阿里云往返
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
        chunk_lists = list(pool.map(_run_batch, jobs))

    return '\n\n'.join(chunk for chunks in chunk_lists for chunk in chunks)
