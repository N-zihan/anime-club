"""
动漫社官网 · 更新日志模块
====================================
从 GitHub API 拉取 commit 记录，过滤出适合展示给用户的内容。
"""
import os
from datetime import datetime, timedelta

import requests

# 内存缓存
_cache = {'data': None, 'expires': None}
CACHE_TTL = 3600  # 1 小时

# 内部维护类 commit，不展示
EXCLUDE_PREFIXES = (
    'chore:', 'ci:', 'test:', 'docs:', 'style:', 'build:', 'revert:',
    'chore：', 'ci：', 'test：', 'docs：',
    'Merge', 'merge',
)

# 用户关心的 commit
INCLUDE_PREFIXES = (
    'feat:', 'fix:', 'perf:', 'refactor:',
    'feat：', 'fix：', 'perf：', 'refactor：',
    '新增', '修复', '优化', '更新', '添加', '重构',
)

# 纯代码整理类关键词，即使匹配前缀也过滤
EXCLUDE_KEYWORDS = (
    'import', '格式', '命名', '注释', 'docstring', '变量名',
    '缩进', 'lint', 'pylint', '空格', '换行',
)


def should_show(message: str) -> bool:
    """判断 commit message 是否适合展示给用户"""
    msg = message.strip()
    if not msg:
        return False
    if msg.startswith(EXCLUDE_PREFIXES):
        return False
    lower = msg.lower()
    if any(kw in lower for kw in EXCLUDE_KEYWORDS):
        return False
    if msg.startswith(INCLUDE_PREFIXES):
        return True
    return False


def get_recent_commits(limit: int = 20) -> list:
    """获取最近的 commits，过滤后返回"""
    if _cache['data'] and _cache['expires'] > datetime.now():
        return _cache['data']

    repo = os.getenv('GITHUB_REPO', 'N-zihan/anime-club')
    url = f'https://api.github.com/repos/{repo}/commits?per_page={limit}'
    headers = {'Accept': 'application/vnd.github.v3+json'}

    token = os.getenv('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'token {token}'

    try:
        res = requests.get(url, headers=headers, timeout=5)
        commits = res.json()

        data = []
        for c in commits:
            first_line = c['commit']['message'].split('\n')[0].strip()
            if not should_show(first_line):
                continue

            clean_msg = first_line
            for prefix in INCLUDE_PREFIXES:
                if clean_msg.startswith(prefix):
                    clean_msg = clean_msg[len(prefix):].strip()
                    break

            data.append({
                'message': clean_msg,
                'date': c['commit']['author']['date'][:10],
                'sha': c['sha'][:7],
                'url': c['html_url'],
            })

        _cache['data'] = data
        _cache['expires'] = datetime.now() + timedelta(seconds=CACHE_TTL)
        return data
    except Exception:
        return []
