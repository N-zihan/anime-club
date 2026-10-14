"""
动漫社官网 · 动漫新闻数据源
====================================
从自部署的 AniNewsAPI 聚合动漫新闻，并翻译标题为中文。
"""
import json
import os
import traceback
from datetime import datetime, timedelta

import requests
from openai import OpenAI

import re
from bs4 import BeautifulSoup

ANI_NEWS_API = 'https://anime-news.nanyi-anime-club.top/'

# 免费模型（SiliconFlow 上 Qwen2.5-7B 免费额度足够翻译标题）
FREE_MODEL = os.getenv('AI_MODEL_FREE', 'Qwen/Qwen2.5-7B-Instruct')

_cache = {}
_CACHE_TTL = 1800  # 新闻缓存 30 分钟
_translate_cache = {}
_TRANSLATE_TTL = 86400  # 翻译缓存 24 小时（翻译结果不会变）


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

        # ★ 关键：批量翻译标题
        if articles:
            titles = [a.get('title', '') for a in articles if a.get('title')]
            if titles:
                translated = _translate_titles(titles)
                for a in articles:
                    orig = a.get('title', '')
                    a['title_zh'] = translated.get(orig, orig)

        result = (articles, meta)
        _cache[cache_key] = (result, now + timedelta(seconds=_CACHE_TTL))
        return result

    except Exception as e:
        print(f'>>> AniNews 请求失败: {e}')
        traceback.print_exc()
        return [], {}


def _translate_titles(titles):
    """批量翻译标题（英→中），带 24 小时内存缓存"""
    result = {}
    to_translate = []

    for t in titles:
        cached = _translate_cache.get(t)
        if cached:
            result[t] = cached
        else:
            to_translate.append(t)

    if not to_translate:
        return result

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        for t in to_translate:
            result[t] = t
        return result

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv('OPENAI_BASE_URL', 'https://api.siliconflow.cn/v1'),
        )

        prompt = (
            "把下面的动漫新闻标题翻译成简体中文。"
            "要求：简洁、准确，保留专有名词。"
            "只返回 JSON，格式为 {\"原文\": \"中文\"}，不要加任何解释或代码块标记。\n\n"
            + json.dumps(to_translate, ensure_ascii=False)
        )

        response = client.chat.completions.create(
            model=FREE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.2,
        )

        text = response.choices[0].message.content.strip()

        # 兜底清理：去掉 ```json ... ``` 包裹
        if text.startswith('```'):
            text = text.split('```', 1)[1]
            if text.lower().startswith('json'):
                text = text[4:]
            text = text.rsplit('```', 1)[0].strip()

        translated = json.loads(text)

        for orig in to_translate:
            zh = translated.get(orig) or orig
            result[orig] = zh
            _translate_cache[orig] = zh

    except Exception as e:
        print(f'>>> 翻译失败: {type(e).__name__}: {e}')
        for t in to_translate:
            result[t] = t

    return result


# 正文缓存（2 天）
_article_cache = {}
_ARTICLE_TTL = 172800

# 抓取时伪装成浏览器
_UA = 'Mozilla/5.0 (compatible; nanyi-anime-club/1.0)'


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

        # 删掉无关标签
        for tag in soup(['script', 'style', 'nav', 'header', 'footer',
                         'aside', 'form', 'iframe', 'noscript', 'button']):
            tag.decompose()

        # 尝试定位正文区
        article = (
            soup.find('article') or
            soup.find('main') or
            soup.find('div', class_=re.compile(r'(article|content|post|entry)', re.I)) or
            soup.body
        )

        if not article:
            return None

        # 提取段落
        paragraphs = []
        for p in article.find_all(['p', 'h2', 'h3']):
            text = p.get_text(' ', strip=True)
            if text and len(text) > 20:
                paragraphs.append(text)

        # 去重 + 拼接
        seen = set()
        cleaned = []
        for p in paragraphs:
            if p not in seen:
                seen.add(p)
                cleaned.append(p)

        full_text = '\n\n'.join(cleaned[:40])  # 最多取 40 段，防止太长

        if len(full_text) < 100:
            return None

        # 翻译
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
    """翻译整篇文章（分段翻译，避免超长）"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return text

    # 按段落切分，每批 5 段
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    BATCH = 5
    translated_parts = []

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv('OPENAI_BASE_URL', 'https://api.siliconflow.cn/v1'),
        )

        for i in range(0, len(paragraphs), BATCH):
            batch = paragraphs[i:i + BATCH]
            prompt = (
                "把下面的动漫新闻段落翻译成简体中文。保持段落结构，"
                "直接返回翻译结果，段落之间用空行分隔。不要加任何解释或前后缀。\n\n"
                + '\n\n'.join(batch)
            )
            resp = client.chat.completions.create(
                model=FREE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.2,
            )
            translated_parts.append(resp.choices[0].message.content.strip())

        return '\n\n'.join(translated_parts)

    except Exception as e:
        print(f'>>> 整篇翻译失败: {e}')
        return text
