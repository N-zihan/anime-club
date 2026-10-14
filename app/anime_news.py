"""
动漫社官网 · 动漫新闻数据源
====================================
从自部署的 AniNewsAPI 聚合动漫新闻。
"""
import traceback
import requests
from datetime import datetime, timedelta
import os
import json
from openai import OpenAI

_translate_cache = {}

ANI_NEWS_API = 'https://ani-news-api-eta.vercel.app'

_cache = {}
_CACHE_TTL = 1800


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

        result = (articles, meta)
        _cache[cache_key] = (result, now + timedelta(seconds=_CACHE_TTL))
        return result

    except Exception as e:
        print(f'>>> AniNews 请求失败: {e}')
        traceback.print_exc()
        return [], {}


def _translate_titles(titles):
    """批量翻译标题（英→中），带缓存"""
    # 先查缓存
    result = {}
    to_translate = []
    for t in titles:
        if t in _translate_cache:
            result[t] = _translate_cache[t]
        else:
            to_translate.append(t)

    if not to_translate:
        return result

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        # 没配 API，直接返回原文
        for t in to_translate:
            result[t] = t
        return result

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv('OPENAI_BASE_URL', 'https://api.siliconflow.cn/v1')
        )
        prompt = (
            "把下面的动漫新闻标题翻译成简体中文。保持简洁，不要意译过度。"
            "只返回 JSON，格式：{\"原文\": \"中文\"}，不要加解释。\n\n"
            + json.dumps(to_translate, ensure_ascii=False)
        )
        response = client.chat.completions.create(
            model=os.getenv('AI_MODEL', 'deepseek-ai/DeepSeek-V3'),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.3,
        )
        text = response.choices[0].message.content.strip()
        # 去掉可能的 ```json ``` 包裹
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        text = text.strip()

        translated = json.loads(text)
        for orig in to_translate:
            zh = translated.get(orig, orig)
            result[orig] = zh
            _translate_cache[orig] = zh

    except Exception as e:
        print(f'>>> 翻译失败: {e}')
        for t in to_translate:
            result[t] = t

    return result