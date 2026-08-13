"""
AI 解说与预测模块
====================================
为萌战赛事提供 AI 生成的实时战报和赛事预测。
使用 SiliconFlow API（兼容 OpenAI 格式）。
"""

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from openai import OpenAI

from .models import Contest, Candidate, ContestVote, db

# 延迟初始化客户端
_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 未配置，无法使用 AI 功能")
        _client = OpenAI(
            api_key=api_key,
            base_url=os.getenv('OPENAI_BASE_URL', 'https://api.siliconflow.cn/v1')
        )
    return _client

# 内存缓存
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_ENABLED = os.getenv('AI_CACHE_ENABLED', 'true').lower() == 'true'
CACHE_TTL = int(os.getenv('AI_CACHE_TTL', 3600))


def _get_cache_key(contest_id: int, phase: str, mode: str) -> str:
    """生成缓存键"""
    data = f"{contest_id}_{phase}_{mode}"
    return hashlib.md5(data.encode()).hexdigest()


def _get_cached(key: str) -> Optional[str]:
    """从缓存获取"""
    if not CACHE_ENABLED:
        return None
    if key in _cache:
        entry = _cache[key]
        if datetime.now() < entry['expires']:
            return entry['data']
        del _cache[key]
    return None


def _set_cache(key: str, data: str):
    """存入缓存"""
    if not CACHE_ENABLED:
        return
    _cache[key] = {
        'data': data,
        'expires': datetime.now() + timedelta(seconds=CACHE_TTL)
    }


def _get_top_votes(contest_id: int, limit: int = 10) -> list:
    """获取票数前 N 名"""
    candidates = Candidate.query.filter_by(contest_id=contest_id).all()
    result = []
    for c in candidates:
        total = ContestVote.query.filter_by(
            candidate_id=c.id, round_number=0
        ).with_entities(db.func.sum(ContestVote.weight)).scalar() or 0
        result.append((c.name, total))
    result.sort(key=lambda x: x[1], reverse=True)
    return result[:limit]


def _build_prompt(contest: Contest, phase: str, phase_name: str, mode: str) -> str:
    """构建 prompt"""
    candidates = contest.candidates.all()
    top_votes = _get_top_votes(contest.id)

    lines = []
    lines.append(f"赛事：{contest.title}")
    lines.append(f"阶段：{phase_name}")
    lines.append(f"候选角色数：{len(candidates)}")
    if top_votes:
        lines.append(f"当前票数前5名：{', '.join([f'{name}({v}票)' for name, v in top_votes[:5]])}")

    if mode == 'commentary':
        return f"""
你是一个二次元萌战赛事的解说员，风格热情、活泼。

当前赛事数据：
{chr(10).join(lines)}

请根据以上数据，生成一段 100-150 字的实时战报解说。要求：
1. 语气自然流畅，像体育解说员在直播
2. 提到 1-2 个关键角色或看点
3. 不要编造数据
4. 直接输出内容，不要加标题
"""
    else:  # prediction
        return f"""
你是一个二次元萌战赛事的预测专家。

当前赛事数据：
{chr(10).join(lines)}

请给出以下预测：
1. 当前趋势分析
2. 最终冠军预测
3. 预测理由（简短）

格式：用 - 开头列出，每条附一句话理由，总共 150-200 字。
"""


def generate_commentary(contest_id: int, phase: str) -> tuple:
    """生成实时战报"""
    try:
        contest = db.session.get(Contest, contest_id)
        if not contest:
            return False, None, "赛事不存在"

        # ====== 赛事未开始时直接返回提示 ======
        if phase == 'not_started':
            return True, "赛事尚未开始，AI 解说将在提名期启动后自动开启。请于 10 月 1 日 18:00 后回来查看！", None
        # ====================================

        # 检查缓存
        cache_key = _get_cache_key(contest_id, phase, 'commentary')
        cached = _get_cached(cache_key)
        if cached:
            return True, cached, None

        # 阶段名称映射
        phase_names = {
            'nomination': '提名期', 'review': '审核期',
            'qualifying': '海选投票', 'qualifying_result': '海选公示',
            'group_round_1': '小组赛第1轮', 'group_round_2': '小组赛第2轮',
            'group_round_3': '小组赛第3轮', 'knockout_16': '淘汰赛16强',
            'knockout_8': '淘汰赛8强', 'knockout_4': '淘汰赛4强',
            'final_vote': '决赛投票', 'final_result': '决赛结果',
            'closed': '已结束'
        }
        phase_name = phase_names.get(phase, phase)

        prompt = _build_prompt(contest, phase, phase_name, 'commentary')

        # ====== 获取客户端并调用 API ======
        client = get_client()
        response = client.chat.completions.create(
            model=os.getenv('AI_MODEL', 'deepseek-ai/DeepSeek-V3'),
            messages=[
                {"role": "system", "content": "你是一个二次元萌战解说员。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.8
        )

        content = response.choices[0].message.content
        _set_cache(cache_key, content)
        return True, content, None

    except Exception as e:
        return False, None, str(e)


def generate_prediction(contest_id: int) -> tuple:
    """生成赛事预测"""
    try:
        contest = db.session.get(Contest, contest_id)
        if not contest:
            return False, None, "赛事不存在"

        # ====== 赛事未开始时直接返回提示 ======
        if contest.status == 'draft':
            return True, "赛事尚未开始，AI 预测将在比赛启动后开启。请于 10 月 1 日 18:00 后回来查看！", None
        # ======================================

        cache_key = _get_cache_key(contest_id, contest.status, 'prediction')
        cached = _get_cached(cache_key)
        if cached:
            return True, cached, None

        phase_names = {
            'nomination': '提名期', 'review': '审核期',
            'qualifying': '海选投票', 'group_stage': '小组赛',
            'knockout': '淘汰赛', 'closed': '已结束'
        }
        phase_name = phase_names.get(contest.status, contest.status)

        prompt = _build_prompt(contest, contest.status, phase_name, 'prediction')

        # ====== 获取客户端并调用 API ======
        client = get_client()
        response = client.chat.completions.create(
            model=os.getenv('AI_MODEL', 'deepseek-ai/DeepSeek-V3'),
            messages=[
                {"role": "system", "content": "你是一个二次元萌战预测专家。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.7
        )

        content = response.choices[0].message.content
        _set_cache(cache_key, content)
        return True, content, None

    except Exception as e:
        return False, None, str(e)
