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
    if sort in ('rank', 'date'):
        # 老接口
        try:
            res = requests.get(
                'https://api.bgm.tv/v0/subjects',
                params={'type': 2, 'sort': sort, 'limit': limit, 'offset': offset},
                headers=HEADERS,
                timeout=8,
            )
            data = res.json()
            items = data.get('data') if isinstance(data, dict) else data
            if not isinstance(items, list):
                return []
            return [_format_item(x) for x in items]
        except Exception as e:
            print(f'Bangumi 拉取失败: {e}')
            return []

    # 搜索接口（heat / score）
    try:
        res = requests.post(
            'https://api.bgm.tv/v0/search/subjects',
            params={'limit': limit, 'offset': offset},
            json={'keyword': '', 'filter': {'type': [2]}, 'sort': sort},
            headers={**HEADERS, 'Content-Type': 'application/json'},
            timeout=8,
        )
        data = res.json()
        items = data.get('data') if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [_format_item(x) for x in items]
    except Exception as e:
        print(f'Bangumi 搜索失败: {e}')
        return []


def search_subjects(keyword, offset=0, limit=PAGE_SIZE, sort='match'):
    """搜索番剧，返回 (结果列表, 总数)"""
    # Bangumi 搜索接口只支持 match/heat/rank/score
    if sort not in ('match', 'heat', 'rank', 'score'):
        sort = 'match'
    try:
        res = requests.post(
            'https://api.bgm.tv/v0/search/subjects',
            params={'limit': limit, 'offset': offset},
            json={'keyword': keyword, 'filter': {'type': [2]}, 'sort': sort},
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


def get_subject_detail(subject_id):
    """拉取单个条目的完整详情"""
    try:
        res = requests.get(
            f'https://api.bgm.tv/v0/subjects/{subject_id}',
            headers=HEADERS,
            timeout=8,
        )
        d = res.json()
        if not isinstance(d, dict) or d.get('id') is None:
            return None

        images = d.get('images') or {}
        rating = d.get('rating') or {}

        # 从 infobox 提取制作人员
        staff_keys = ('导演', '原作', '脚本', '系列构成', '分镜', '演出',
                      '音乐', '人物设定', '美术监督', '动画制作', '制作')
        staff = []
        for item in (d.get('infobox') or []):
            key = item.get('key')
            if key in staff_keys:
                val = item.get('value')
                if isinstance(val, list):
                    val = '、'.join(
                        str(v.get('v', v)) if isinstance(v, dict) else str(v)
                        for v in val
                    )
                staff.append({'key': key, 'value': val})

        return {
            'id': d.get('id'),
            'name': d.get('name_cn') or d.get('name') or '',
            'original_name': d.get('name') or '',
            'summary': (d.get('summary') or '').strip(),
            'cover': images.get('large') or images.get('common') or '',
            'score': rating.get('score') or 0,
            'rank': rating.get('rank') or 0,
            'total': rating.get('total') or 0,
            'date': d.get('date') or '',
            'eps': d.get('eps') or d.get('total_episodes') or 0,
            'platform': d.get('platform') or '',
            'staff': staff,
        }
    except Exception as e:
        print(f'Bangumi 详情拉取失败: {e}')
        return None
