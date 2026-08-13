"""
AI 解说与预测模块
====================================
为萌战赛事提供 AI 生成的实时战报和赛事预测。
使用 SiliconFlow API（兼容 OpenAI 格式）。
"""

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

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


def _get_cache_key(contest_id: int, phase: str, mode: str, round_info: str = '') -> str:
    """生成缓存键"""
    data = f"{contest_id}_{phase}_{mode}_{round_info}"
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


def _get_qualifying_top_votes(contest_id: int, limit: int = 10) -> list:
    """获取海选票数前 N 名"""
    candidates = Candidate.query.filter_by(contest_id=contest_id).all()
    result = []
    for c in candidates:
        total = ContestVote.query.filter_by(
            candidate_id=c.id, round_number=0
        ).with_entities(db.func.sum(ContestVote.weight)).scalar() or 0
        result.append((c.id, c.name, total))
    result.sort(key=lambda x: x[2], reverse=True)
    return result[:limit]


def _build_commentary_prompt(contest: Contest, phase: str, phase_name: str, extra_data: dict = None) -> str:
    """根据阶段构建不同的 prompt"""
    if phase == 'nomination':
        return _build_nomination_prompt(contest)
    elif phase == 'qualifying':
        return _build_qualifying_prompt(contest)
    elif phase in ['group_round_1', 'group_round_2', 'group_round_3']:
        return _build_group_prompt(contest, phase, extra_data)
    elif phase in ['knockout_16', 'knockout_8', 'knockout_4', 'final_vote']:
        return _build_knockout_prompt(contest, phase, extra_data)
    elif phase == 'final_result':
        return _build_final_prompt(contest)
    else:
        return _build_generic_prompt(contest, phase_name)


def _build_nomination_prompt(contest: Contest) -> str:
    """提名期 prompt"""
    nominations = contest.nominations.filter_by(status='approved').count()
    pending = contest.nominations.filter_by(status='pending').count()
    return f"""
你是萌战解说员，正在解说"提名期"。

赛事：{contest.title}
已通过提名：{nominations} 个角色
待审核提名：{pending} 个角色

请用热情活泼的语气，生成一段 80-100 字的提名期战报。
要点：
- 提到提名总数
- 鼓励大家积极提名
- 语气要有"赛事即将开始"的期待感
"""


def _build_qualifying_prompt(contest: Contest) -> str:
    """海选投票期 prompt"""
    top = _get_qualifying_top_votes(contest.id, 8)
    total_candidates = contest.candidates.count()

    if not top:
        return "海选投票已开启，但目前还没有票数记录。"

    lines = []
    lines.append(f"赛事：{contest.title}")
    lines.append(f"候选角色数：{total_candidates}")
    lines.append("当前票数排名：")
    for i, (cid, name, votes) in enumerate(top, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        lines.append(f"  {medal} {name}：{votes}票")

    if len(top) < total_candidates:
        lines.append(f"... 还有 {total_candidates - len(top)} 名选手正在追赶")

    return f"""
你是萌战解说员，正在解说"海选投票"。

当前数据：
{chr(10).join(lines)}

请根据以上数据，生成一段 100-150 字的海选战报。
要求：
1. 提到前3名的角色和票数
2. 指出领先者的优势或追赶者的态势
3. 语气热情、有紧张感
4. 不要编造数据
"""


def _build_group_prompt(contest: Contest, phase: str, extra_data: dict) -> str:
    """小组赛阶段 prompt"""
    if not extra_data:
        return "小组赛数据加载中，请稍后再看 AI 分析。"

    gender = extra_data.get('gender', 'female')
    groups = extra_data.get('groups', [])
    group_results = extra_data.get('group_results', {})

    gender_name = "女组" if gender == 'female' else "男组"

    lines = []
    lines.append(f"赛事：{contest.title}")
    lines.append(f"阶段：{gender_name} 小组赛")

    # 构建分组信息
    group_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    for idx, group in enumerate(groups[:8]):  # 最多8组
        if idx >= len(group_names):
            break
        group_name = group_names[idx]
        matches = group_results.get(idx, [])
        lines.append(f"\n{group_name}组：")
        if matches:
            for match in matches:
                c1 = match.get('candidate1')
                c2 = match.get('candidate2')
                v1 = match.get('votes1', 0)
                v2 = match.get('votes2', 0)
                winner = match.get('winner')
                if c1 and c2:
                    win_mark = "🏆" if winner == c1.id else ""
                    lines.append(f"  {c1.name}({v1}票) VS {c2.name}({v2}票){win_mark}")
        else:
            lines.append("  暂无比赛数据")

    # 积分排名（如果有）
    ranking = extra_data.get('ranking', [])
    if ranking:
        lines.append("\n当前积分排名（前5）：")
        for i, item in enumerate(ranking[:5], 1):
            lines.append(f"  {i}. {item.get('name')}：{item.get('points')}分")

    return f"""
你是萌战解说员，正在解说小组赛。

当前数据：
{chr(10).join(lines)}

请根据以上数据，生成一段 120-180 字的小组赛战报。
要求：
1. 突出各组的关键对决
2. 分析各组的出线形势
3. 提到 1-2 个亮点选手
4. 语气要像真正的赛事解说
5. 不要编造数据
"""


def _build_knockout_prompt(contest: Contest, phase: str, extra_data: dict) -> str:
    """淘汰赛阶段 prompt"""
    if not extra_data:
        return "淘汰赛数据加载中，请稍后再看 AI 分析。"

    gender = extra_data.get('gender', 'female')
    matches = extra_data.get('matches', [])

    gender_name = "女组" if gender == 'female' else "男组"
    round_names = {
        'knockout_16': '16强',
        'knockout_8': '8强',
        'knockout_4': '4强',
        'final_vote': '决赛'
    }
    round_name = round_names.get(phase, '淘汰赛')

    lines = []
    lines.append(f"赛事：{contest.title}")
    lines.append(f"阶段：{gender_name} {round_name}")

    if not matches:
        return f"{round_name}对阵尚未生成，请稍后再看 AI 分析。"

    lines.append("\n当前对阵及票数：")
    for i, match in enumerate(matches, 1):
        c1_name = match.get('candidate1_name', '选手A')
        c2_name = match.get('candidate2_name', '选手B')
        v1 = match.get('votes1', 0)
        v2 = match.get('votes2', 0)
        status = match.get('status', 'active')
        if status == 'finished' and match.get('winner'):
            winner_name = match.get('winner_name', '')
            lines.append(f"  {i}. {c1_name}({v1}票) VS {c2_name}({v2}票) → 🏆 {winner_name} 晋级")
        else:
            lines.append(f"  {i}. {c1_name}({v1}票) VS {c2_name}({v2}票) — 进行中")

    return f"""
你是萌战解说员，正在解说淘汰赛。

当前数据：
{chr(10).join(lines)}

请根据以上数据，生成一段 120-180 字的淘汰赛战报。
要求：
1. 分析各场比赛的形势
2. 预测可能晋级的人选
3. 提到票数接近的焦点对决
4. 语气紧张、有激情
5. 不要编造数据
"""


def _build_final_prompt(contest: Contest) -> str:
    """决赛结果 prompt"""
    ranking_female = contest.config.get('female_ranking', []) if contest.config else []
    ranking_male = contest.config.get('male_ranking', []) if contest.config else []

    lines = []
    lines.append(f"赛事：{contest.title}")
    lines.append("🏆 最终排名：")

    if ranking_female:
        lines.append("\n女组冠军：")
        champion = ranking_female[0] if ranking_female else {}
        lines.append(f"  🥇 {champion.get('name', '未知')}（{champion.get('votes', 0)}票）")
        if len(ranking_female) >= 2:
            runner = ranking_female[1]
            lines.append(f"  🥈 {runner.get('name', '未知')}（{runner.get('votes', 0)}票）")

    if ranking_male:
        lines.append("\n男组冠军：")
        champion = ranking_male[0] if ranking_male else {}
        lines.append(f"  🥇 {champion.get('name', '未知')}（{champion.get('votes', 0)}票）")
        if len(ranking_male) >= 2:
            runner = ranking_male[1]
            lines.append(f"  🥈 {runner.get('name', '未知')}（{runner.get('votes', 0)}票）")

    return f"""
你是萌战解说员，正在总结赛事。

当前数据：
{chr(10).join(lines)}

请生成一段 80-120 字的赛事总结。
要求：
1. 祝贺冠军
2. 总结赛事亮点
3. 语气温暖、有仪式感
"""


def _build_generic_prompt(contest: Contest, phase_name: str) -> str:
    """通用 prompt（兜底）"""
    return f"""
你是萌战解说员。

赛事：{contest.title}
阶段：{phase_name}

请生成一段 60-80 字的简短战报，说明当前赛事状态。
"""


def generate_commentary(contest_id: int, phase: str, extra_data: dict = None) -> tuple:
    """生成实时战报"""
    try:
        contest = db.session.get(Contest, contest_id)
        if not contest:
            return False, None, "赛事不存在"

        if phase == 'not_started':
            return True, "赛事尚未开始，AI 解说将在提名期启动后自动开启。请于 10 月 1 日 18:00 后回来查看！", None

        # 检查缓存
        round_info = extra_data.get('round_info', '') if extra_data else ''
        cache_key = _get_cache_key(contest_id, phase, 'commentary', round_info)
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

        prompt = _build_commentary_prompt(contest, phase, phase_name, extra_data)

        # 如果 prompt 返回的是纯文本（非结构化），直接返回
        if prompt.startswith("海选投票已开启") or prompt.startswith("小组赛数据加载中") or prompt.startswith("淘汰赛数据加载中"):
            return True, prompt, None

        client = get_client()
        response = client.chat.completions.create(
            model=os.getenv('AI_MODEL', 'deepseek-ai/DeepSeek-V3'),
            messages=[
                {"role": "system", "content": "你是一个二次元萌战赛事的专业解说员，风格热情、活泼、略带中二。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.8
        )

        content = response.choices[0].message.content
        _set_cache(cache_key, content)
        return True, content, None

    except Exception as e:
        return False, None, str(e)


def generate_prediction(contest_id: int, extra_data: dict = None) -> tuple:
    """生成赛事预测"""
    try:
        contest = db.session.get(Contest, contest_id)
        if not contest:
            return False, None, "赛事不存在"

        if contest.status == 'draft':
            return True, "赛事尚未开始，AI 预测将在比赛启动后开启。请于 10 月 1 日 18:00 后回来查看！", None

        cache_key = _get_cache_key(contest_id, contest.status, 'prediction')
        cached = _get_cached(cache_key)
        if cached:
            return True, cached, None

        # 构建预测 prompt
        top = _get_qualifying_top_votes(contest.id, 10)
        lines = []
        lines.append(f"赛事：{contest.title}")
        lines.append(f"状态：{contest.status}")
        lines.append("\n海选票数前10名：")
        for i, (cid, name, votes) in enumerate(top, 1):
            lines.append(f"  {i}. {name}：{votes}票")

        prompt = f"""
你是萌战预测专家。

当前数据：
{chr(10).join(lines)}

请给出以下预测：
1. 最终冠军预测（男女组各一个）
2. 冠军预测理由（2-3点）
3. 可能出现的黑马角色

格式：用 - 开头列出，总共 150-200 字。
"""

        client = get_client()
        response = client.chat.completions.create(
            model=os.getenv('AI_MODEL', 'deepseek-ai/DeepSeek-V3'),
            messages=[
                {"role": "system", "content": "你是一个二次元萌战赛事的预测专家，分析理性但语气有趣。"},
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
