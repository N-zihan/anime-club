"""
动漫社官网 · 番剧百科数据源
====================================
从 Bangumi API 拉取番剧，支持分页浏览和搜索。
"""
import requests

HEADERS = {
    'User-Agent': 'nanyi-anime-club/1.0 (https://www.nanyi-anime-club.top)',
}

PAGE_SIZE = 25


def _format_item(item):
    """把 Bangumi 的条目格式化成前端要用的字段"""
    images = item.get('images') or {}
    rating = item.get('rating') or {}
    return {
        'id': item.get('id'),
        'name': item.get('name_cn') or item.get('name') or '',
        'original_name': item.get('name') or '',
        'summary': (item.get('summary') or '').strip(),
        'cover': images.get('common') or images.get('large') or '',
        'score': rating.get('score') or 0,
        'rank': item.get('rank') or 0,
        'date': item.get('date') or '',
        'eps': item.get('eps') or item.get('eps_count') or 0,
    }


def get_subjects(offset=0, limit=PAGE_SIZE, sort='rank'):
    """分页获取番剧列表（type=2 表示动画）"""
    try:
        res = requests.get(
            'https://api.bgm.tv/v0/subjects',
            params={'type': 2, 'sort': sort, 'limit': limit, 'offset': offset},
            headers=HEADERS,
            timeout=8,
        )
        data = res.json()
        # /v0/subjects 返回 Paged 格式：{"data": [...], "total": N}
        items = data.get('data') if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return [_format_item(x) for x in items]
    except Exception as e:
        print(f'Bangumi 拉取失败: {e}')
        return []


def search_subjects(keyword, offset=0, limit=PAGE_SIZE):
    """搜索番剧，返回 (结果列表, 总数)"""
    try:
        res = requests.post(
            'https://api.bgm.tv/v0/search/subjects',
            params={'limit': limit, 'offset': offset},
            json={'keyword': keyword, 'filter': {'type': [2]}, 'sort': 'match'},
            headers={**HEADERS, 'Content-Type': 'application/json'},
            timeout=8,
        )
        data = res.json()
        items = data.get('data') or []
        total = data.get('total') or 0
        return [_format_item(x) for x in items], total
    except Exception as e:
        print(f'Bangumi 搜索失败: {e}')
        return [], 0
