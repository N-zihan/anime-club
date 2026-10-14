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
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ANI_NEWS_API = 'https://anime-news.nanyi-anime-club.top/'

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
        res = requests.get(_ALIYUN_MT_ENDPOINT, params=params, timeout=10)
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

    for batch in batches:
        # 单条超长的情况，直接单独调用
        if len(batch) == 1 and len(batch[0]) > _ALIYUN_SINGLE_MAX:
            # 截断处理（超过 4500 字符的文本很少见）
            truncated = batch[0][:_ALIYUN_SINGLE_MAX]
            translated = _aliyun_call(truncated)
            if translated:
                result[batch[0]] = translated
                _translate_cache[batch[0]] = translated
            else:
                result[batch[0]] = batch[0]
            continue

        joined = '\n'.join(batch)
        translated = _aliyun_call(joined)

        if translated is None:
            # 调用失败，原样返回
            for t in batch:
                result[t] = t
            continue

        lines = translated.split('\n')

        # 行数不匹配时，降级为逐条翻译
        if len(lines) != len(batch):
            print(f'>>> 行数不匹配（{len(lines)} vs {len(batch)}），降级逐条翻译')
            for t in batch:
                single = _aliyun_call(t)
                zh = single if single else t
                result[t] = zh
                _translate_cache[t] = zh
            continue

        for orig, trans in zip(batch, lines):
            zh = trans.strip() or orig
            result[orig] = zh
            _translate_cache[orig] = zh

    return result


# ============================================================
# 新闻列表
# ============================================================
def get_anime_news(limit=20, tag=None, cursor=None):
    """获取动漫新闻列表，返回 (articles, meta)"""
    cache_key = f'news_{limit}_{tag or "all"}_{cursor or "start"}'
    now = datetime.now()

    if cache_key in _cache:
        data, expires = _cache[cache_key]
        if now < expires:
            return data

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

    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in keyword)

    articles, _ = get_anime_news(limit=100)

    keywords = [keyword.lower()]

    if has_chinese:
        translated = _translate_keyword(keyword)
        if translated and translated.lower() != keyword.lower():
            keywords.append(translated.lower())
            print(f'>>> 搜索词翻译: "{keyword}" → "{translated}"')

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
        res = requests.get(url, headers={'User-Agent': _UA}, timeout=15)
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

        result = {
            'title': soup.title.string.strip() if soup.title and soup.title.string else '',
            'content': translated,
        }
        _article_cache[url] = (result, now + timedelta(seconds=_ARTICLE_TTL))
        return result

    except Exception as e:
        print(f'>>> 解析原文失败: {e}')
        traceback.print_exc()
        return None


def _translate_article(text):
    """翻译整篇文章。按段落分批调用阿里云。"""
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    if not paragraphs:
        return text

    translated_parts = []
    BATCH_SIZE = 5  # 每批 5 段

    for i in range(0, len(paragraphs), BATCH_SIZE):
        batch = paragraphs[i:i + BATCH_SIZE]
        joined = '\n'.join(batch)

        # 超过单次限制的段落单独处理
        if len(joined) > _ALIYUN_SINGLE_MAX:
            for p in batch:
                if len(p) > _ALIYUN_SINGLE_MAX:
                    p = p[:_ALIYUN_SINGLE_MAX]
                single = _aliyun_call(p)
                translated_parts.append(single if single else p)
            continue

        translated = _aliyun_call(joined)
        if translated:
            translated_parts.append(translated)
        else:
            translated_parts.append('\n'.join(batch))

    return '\n\n'.join(translated_parts)
