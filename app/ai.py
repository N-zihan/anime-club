"""
AI 解说与预测模块
====================================

为萌战赛事提供 AI 生成的实时战报和赛事预测。
使用 SiliconFlow API（兼容 OpenAI 格式）。
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from openai import OpenAI

from .models import Contest, Candidate, ContestVote, db

logger = logging.getLogger(__name__)

# 延迟初始化客户端
_client = None # pylint: disable=invalid-name


def get_client():
    global _client # pylint: disable=global-statement
    if _client is None:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 未配置，无法使用 AI 功能")
        _client = OpenAI(
            api_key=api_key,
            base_url=os.getenv('OPENAI_BASE_URL', 'https://api.siliconflow.cn/v1'),
            # 显式超时：SDK 默认 600s 且自动重试 2 次，而 Vercel 函数 30s 就被强杀，
            # 结果只表现为难以定位的随机 500。
            timeout=float(os.getenv('AI_TIMEOUT', '20')),
            max_retries=0,
        )
    return _client


# 内存缓存
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_ENABLED = os.getenv('AI_CACHE_ENABLED', 'true').lower() == 'true'
CACHE_TTL = int(os.getenv('AI_CACHE_TTL', '3600'))


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


_CACHE_MAX_ENTRIES = int(os.getenv('AI_CACHE_MAX_ENTRIES', '500'))


def _set_cache(key: str, data: str):
    """存入缓存"""
    if not CACHE_ENABLED:
        return
    # 缓存键含用户可控的 phase，必须限制条数，否则可被刷爆实例内存
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        _now = datetime.now()
        for _k in [k for k, v in _cache.items() if v['expires'] <= _now]:
            _cache.pop(_k, None)
        while len(_cache) >= _CACHE_MAX_ENTRIES:
            _cache.pop(next(iter(_cache)), None)
    _cache[key] = {
        'data': data,
        'expires': datetime.now() + timedelta(seconds=CACHE_TTL)
    }


def _get_qualifying_top_votes(contest_id: int, gender: str = None, limit: int = 10) -> list:
    """获取海选票数前 N 名（可按性别过滤）"""
    # 构建基础查询
    query = Candidate.query.filter_by(contest_id=contest_id)
    if gender:
        query = query.filter_by(gender=gender)
    
    # 获取所有候选角色 ID
    candidate_ids = [c.id for c in query.all()]
    
    if not candidate_ids:
        return []
    
    # 一次性查询所有票数
    vote_totals = dict(
        db.session.query(
            ContestVote.candidate_id,
            db.func.sum(ContestVote.weight)
        )
        .filter(
            ContestVote.candidate_id.in_(candidate_ids),
            ContestVote.round_number == 0
        )
        .group_by(ContestVote.candidate_id)
        .all()
    )
    
    # 构建结果列表
    result = []
    for candidate in query.all():
        total = vote_totals.get(candidate.id, 0)
        result.append((candidate.id, candidate.name, total))
    
    # 按票数排序并返回前 N 名
    result.sort(key=lambda x: x[2], reverse=True)
    return result[:limit]


def _build_commentary_prompt(contest: Contest, phase: str, phase_name: str, extra_data: dict = None) -> str:
    """根据阶段构建不同的 prompt"""
    if phase == 'nomination':
        return _build_nomination_prompt(contest)
    if phase == 'review':
        return _build_review_prompt(contest)
    if phase == 'qualifying':
        return _build_qualifying_prompt(contest)
    if phase == 'qualifying_result':
        return _build_qualifying_result_prompt(contest)
    if phase in ['group_round_1', 'group_round_2', 'group_round_3']:
        return _build_group_prompt(contest, phase, extra_data)
    if phase in ['group_round_1_result', 'group_round_2_result', 'group_round_3_result']:
        return _build_group_result_prompt(contest, phase, extra_data)
    if phase in ['knockout_16', 'knockout_8', 'knockout_4', 'final_vote']:
        return _build_knockout_prompt(contest, phase, extra_data)
    if phase in ['knockout_16_result', 'knockout_8_result', 'knockout_4_result']:
        return _build_knockout_result_prompt(contest, phase, extra_data)
    if phase == 'final_result':
        return _build_final_prompt(contest)
    return _build_generic_prompt(contest, phase_name)


def _build_nomination_prompt(contest: Contest) -> str:
    """提名期 prompt"""
    from .models import Nomination, Candidate

    # 用户数：从提名表去重统计（这个没错）
    user_count = db.session.query(Nomination.user_id).filter_by(
        contest_id=contest.id
    ).distinct().count()

    # 角色数：直接从候选池统计，不依赖提名状态
    candidate_count = Candidate.query.filter_by(contest_id=contest.id).count()

    return f"""
你是萌战解说员，正在解说"提名期"。

赛事：{contest.title}

【数据统计】（请严格按以下措辞表述，不要改变单位）
- 已提交提名的用户数：{user_count} 人
- 候选角色数：{candidate_count} 个

请用热情活泼的语气，生成一段 80-100 字的提名期战报。
要点：
- 提到"已有 {user_count} 位社员参与了提名"
- 提到"目前候选池已有 {candidate_count} 个角色"
- 鼓励大家积极提名
- 语气要有"赛事即将开始"的期待感
- 注意区分"用户"和"角色"两个词，不要说反
"""


def _build_review_prompt(contest: Contest) -> str:
    """审核期 prompt"""
    from .models import Nomination, Candidate

    user_count = db.session.query(Nomination.user_id).filter_by(
        contest_id=contest.id
    ).distinct().count()
    candidate_count = Candidate.query.filter_by(contest_id=contest.id).count()
    pending = contest.nominations.filter_by(status='pending').count()

    return f"""
你是萌战解说员，正在解说"审核期"。

赛事：{contest.title}

【数据统计】（请严格按以下措辞表述）
- 参与提名的用户数：{user_count} 人
- 候选角色数：{candidate_count} 个
- 待审核的角色数：{pending} 个

请生成一段 80-100 字的审核期战报。
要点：
- 说明管理员正在审核提名
- 提到"目前候选池已有 {candidate_count} 个角色"
- 语气轻松，让用户稍安勿躁
- 注意区分"用户"和"角色"
"""


def _build_qualifying_prompt(contest: Contest) -> str:
    """海选投票期 prompt"""
    female_top = _get_qualifying_top_votes(contest.id, gender='female', limit=5)
    male_top = _get_qualifying_top_votes(contest.id, gender='male', limit=5)
    female_total = contest.candidates.filter_by(gender='female').count()
    male_total = contest.candidates.filter_by(gender='male').count()

    if not female_top and not male_top:
        return "海选投票已开启，但目前还没有票数记录。"

    lines = [f"赛事：{contest.title}"]

    if female_top:
        lines.append(f"\n【女组】候选 {female_total} 人，当前票数排名：")
        for i, (_, name, votes) in enumerate(female_top, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            lines.append(f"  {medal} {name}：{votes}票")

    if male_top:
        lines.append(f"\n【男组】候选 {male_total} 人，当前票数排名：")
        for i, (_, name, votes) in enumerate(male_top, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            lines.append(f"  {medal} {name}：{votes}票")

    return f"""
你是萌战解说员，正在解说"海选投票"。

当前数据：
{chr(10).join(lines)}

请根据以上数据，生成一段 120-180 字的海选战报。
要求：
1. 男女组分开评论，各提到前 2-3 名的角色和票数
2. 指出领先者的优势或追赶者的态势
3. 语气热情、有紧张感
4. 不要编造数据，不要混淆男女组
"""


def _auto_group_extra_data(contest: Contest, phase: str) -> dict:
    """小组赛阶段自建解说数据。

    /commentary 路由不带 extra_data；contest_detail 的 group_round_results 又
    只在公示期才有值（prepare_group_round_data 对投票期返回 None），直接用会让
    小组赛整个阶段只能回占位文案。这里按轮次现算：投票期取当前累计票数，
    公示期取最终结果，男女组都覆盖。
    """
    from .contest_engine import prepare_group_round_data

    parts = phase.split('_')
    try:
        round_num = int(parts[2])
    except (IndexError, ValueError):
        round_num = 1
    # prepare_* 只认公示期阶段名（其内部查询不受阶段时间限制，投票期同样可用）
    result_phase = f'group_round_{round_num}_result'
    results, rank_f, rank_m = prepare_group_round_data(contest, result_phase)
    results = results or {'female': [], 'male': []}
    config = contest.config or {}

    return {
        'round_info': phase,
        'female': {
            'groups': config.get('female_groups', []) or [],
            'group_results': results.get('female', []),
            'ranking': rank_f or [],
        },
        'male': {
            'groups': config.get('male_groups', []) or [],
            'group_results': results.get('male', []),
            'ranking': rank_m or [],
        },
    }


def _group_section_lines(section: dict, round_num: int) -> list:
    """单个性别的对局与积分数据行"""
    lines = []
    group_results = section.get('group_results') or []
    for group in group_results[:8]:
        group_name = group.get('group_name', '')
        matches = group.get('matches', [])
        if not matches:
            continue
        lines.append(f"\n{group_name}：")
        for m in matches:
            c1 = m.get('candidate1')
            c2 = m.get('candidate2')
            v1 = m.get('votes1', 0)
            v2 = m.get('votes2', 0)
            winner = m.get('winner')
            getter = (lambda c: getattr(c, 'name', '')) if hasattr(c1, 'name') else (lambda c: c)
            c1_name = getter(c1) if c1 else ('轮空' if not m.get('removed1') else '已移除')
            c2_name = getter(c2) if c2 else ('轮空' if not m.get('removed2') else '已移除')
            mark = ""
            if m.get('bye'):
                mark = "（轮空场）"
            elif m.get('banned1') and m.get('banned2'):
                mark = "（双方禁赛，无人晋级）"
            elif m.get('banned1') or m.get('banned2'):
                mark = "（一方禁赛，对手不战而胜）"
            c1_id = getattr(c1, 'id', None)
            if winner is not None and winner == c1_id:
                mark += "🏆"
            lines.append(f"  {c1_name}({v1}票) vs {c2_name}({v2}票){mark}")

    ranking = section.get('ranking') or []
    if ranking:
        lines.append("\n总积分排名（前5）：")
        for i, item in enumerate(ranking[:5], 1):
            extra = "（禁赛）" if item.get('banned') else ""
            lines.append(f"  {i}. {item.get('name')}：{item.get('points')}分{extra}")
    return lines


def _build_group_prompt(contest: Contest, _phase: str, extra_data: dict) -> str:
    """小组赛进行中 prompt"""
    if not extra_data:
        return "小组赛数据加载中，请稍后再看 AI 分析。"

    # 新结构：female/male 各含 groups/group_results/ranking
    if 'female' in extra_data or 'male' in extra_data:
        sections = [(g, extra_data.get(g, {})) for g in ('female', 'male')]
    else:
        # 兼容旧单性别结构
        gender = extra_data.get('gender', 'female')
        sections = [(gender, extra_data)]

    round_num = 1
    parts = (_phase or '').split('_')
    if len(parts) >= 3 and parts[2].isdigit():
        round_num = int(parts[2])

    lines = [f"赛事：{contest.title}", f"阶段：小组赛第{round_num}轮"]
    has_data = False
    for gender, section in sections:
        data_lines = _group_section_lines(section, round_num)
        if data_lines:
            has_data = True
            lines.append("\n【女组】" if gender == 'female' else "\n【男组】")
            lines.extend(data_lines)
    if not has_data:
        return "小组赛数据加载中，请稍后再看 AI 分析。"

    return f"""
你是萌战解说员，正在解说小组赛第{round_num}轮。

当前数据：
{chr(10).join(lines)}

请根据以上数据，生成一段 120-180 字的小组赛战报。
要求：
1. 男女组分开点评（若某组没有数据则略过该组）
2. 突出各组的关键对决和出线形势
3. 提到 1-2 个亮点选手
4. 语气要像真正的赛事解说，不要编造数据
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


def _build_qualifying_result_prompt(contest: Contest) -> str:
    """海选公示期 prompt"""
    female_top = _get_qualifying_top_votes(contest.id, gender='female', limit=5)
    male_top = _get_qualifying_top_votes(contest.id, gender='male', limit=5)

    lines = [f"赛事：{contest.title}", "阶段：海选结果公示"]

    if female_top:
        lines.append("\n【女组】最终票数排名（前5）：")
        for i, (_, name, votes) in enumerate(female_top, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            lines.append(f"  {medal} {name}：{votes}票")

    if male_top:
        lines.append("\n【男组】最终票数排名（前5）：")
        for i, (_, name, votes) in enumerate(male_top, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            lines.append(f"  {medal} {name}：{votes}票")

    return f"""
你是萌战解说员，正在解说"海选结果公示"阶段。

当前数据：
{chr(10).join(lines)}

请根据以上数据，生成一段 150-200 字的海选总结。
要求：
1. 男女组分开总结，各提到前三名的角色和票数
2. 祝贺晋级的角色
3. 预告即将开始的小组赛
4. 语气热情、有期待感
5. 不要编造数据，不要混淆男女组
"""


def _build_group_result_prompt(contest: Contest, phase: str, extra_data: dict) -> str:
    """小组赛公示期 prompt"""
    if not extra_data:
        return "小组赛本轮数据加载中，请稍后再看 AI 分析。"

    round_map = {
        'group_round_1_result': 1,
        'group_round_2_result': 2,
        'group_round_3_result': 3,
    }
    round_num = round_map.get(phase, 1)

    # 新结构：female/male 各含 group_results/ranking；兼容旧单性别结构
    if 'female' in extra_data or 'male' in extra_data:
        sections = [(g, extra_data.get(g, {})) for g in ('female', 'male')]
    else:
        gender = extra_data.get('gender', 'female')
        sections = [(gender, extra_data)]

    lines = [f"赛事：{contest.title}", f"阶段：第{round_num}轮公示"]
    has_data = False
    for gender, section in sections:
        data_lines = _group_section_lines(section, round_num)
        if data_lines:
            has_data = True
            lines.append("\n【女组】" if gender == 'female' else "\n【男组】")
            lines.extend(data_lines)
    if not has_data:
        return "小组赛本轮数据加载中，请稍后再看 AI 分析。"

    return f"""
你是萌战解说员，正在解说小组赛第{round_num}轮的结果公示。

当前数据：
{chr(10).join(lines)}

请生成一段 150-200 字的小组赛总结。
要求：
1. 男女组分开总结（若某组没有数据则略过该组）
2. 突出本轮的精彩对决和出线形势
3. 提到积分榜上的领先者
4. 语气热情、专业，不要编造数据
"""


def _build_knockout_result_prompt(contest: Contest, phase: str, extra_data: dict) -> str:
    """淘汰赛公示期 prompt"""
    if not extra_data:
        return "淘汰赛数据加载中，请稍后再看 AI 分析。"

    gender = extra_data.get('gender', 'female')
    gender_name = "女组" if gender == 'female' else "男组"

    phase_to_name = {
        'knockout_16_result': '16强',
        'knockout_8_result': '8强',
        'knockout_4_result': '4强',
    }
    round_name = phase_to_name.get(phase, '')

    matches = extra_data.get('matches', [])
    if not matches:
        return f"{round_name}结果数据加载中，请稍后再看。"

    lines = [f"赛事：{contest.title}", f"阶段：{gender_name} {round_name}公示", "\n本轮结果："]

    for i, match in enumerate(matches, 1):
        c1_name = match.get('candidate1_name', '选手A')
        c2_name = match.get('candidate2_name', '选手B')
        v1 = match.get('votes1', 0)
        v2 = match.get('votes2', 0)
        winner_name = match.get('winner_name', '')
        lines.append(f"  {i}. {c1_name}({v1}票) vs {c2_name}({v2}票) → 🏆 {winner_name}晋级")

    return f"""
你是萌战解说员，正在解说{round_name}结果。

当前数据：
{chr(10).join(lines)}

请生成一段 120-180 字的总结。
要求：
1. 祝贺晋级的角色
2. 简要点评关键对决
3. 预告下一轮对阵
4. 语气紧张、有激情
5. 不要编造数据
"""


def _build_final_prompt(contest: Contest) -> str:
    """决赛结果 prompt"""
    ranking_female = contest.config.get('female_ranking', []) if contest.config else []
    ranking_male = contest.config.get('male_ranking', []) if contest.config else []

    lines = []
    lines.append(f"赛事：{contest.title}")
    lines.append("最终排名：")

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


def generate_commentary(contest_id: int, phase: str, extra_data: dict = None, force: bool = False) -> tuple:
    """生成实时战报"""
    try:
        contest = db.session.get(Contest, contest_id)
        if not contest:
            return False, None, "赛事不存在"

        if phase == 'not_started':
            return True, "赛事尚未开始，AI 解说将在提名期启动后自动开启。请于 10 月 1 日 18:00 后回来查看！", None

        # 检查缓存（force 跳过）
        round_info = extra_data.get('round_info', '') if extra_data else ''
        cache_key = _get_cache_key(contest_id, phase, 'commentary', round_info)
        if not force:
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

        # 小组赛阶段调用方不带 extra_data（/commentary 路由没有比赛数据可传），
        # 这里按轮次自建男女组数据，否则整个小组赛只能回「数据加载中」占位
        if (extra_data is None and phase.startswith('group_round')):
            extra_data = _auto_group_extra_data(contest, phase)

        prompt = _build_commentary_prompt(contest, phase, phase_name, extra_data)

        # 如果 prompt 是占位文本（没有真实数据），直接返回
        if ('加载中' in prompt or '请稍后再看' in prompt
                or prompt.startswith('海选投票已开启')):
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
        logger.error("AI 解说生成失败: %s", e, exc_info=True)
        return False, None, str(e)


def _prediction_knockout_lines(contest: Contest) -> list:
    """淘汰赛阶段的当前对阵数据行（男女组分开，实时票数）"""
    from .contest_engine import get_knockout_votes

    config = contest.config or {}
    candidates_map = {c.id: c for c in contest.candidates.all()}
    sub_round_map = {'16强': 1, '8强': 2, '4强': 3, '决赛': 4}
    round_order = {'16强': 1, '8强': 2, '4强': 3, '决赛': 4}

    active_round = 0
    for g in ('female', 'male'):
        for m in config.get(f'knockout_matches_{g}', []) or []:
            active_round = max(active_round, round_order.get(m.get('round_name'), 0))
    if not active_round:
        return []
    round_name = {1: '16强', 2: '8强', 3: '4强', 4: '决赛'}[active_round]
    sub_round = sub_round_map[round_name]

    lines = [f"\n当前进行：{round_name}"]
    for gender, label in (('female', '【女组】'), ('male', '【男组】')):
        matches = config.get(f'knockout_matches_{gender}', []) or []
        if not matches:
            continue
        lines.append(f"{label}{round_name}对阵：")
        for m in matches:
            c1 = candidates_map.get(m.get('candidate1'))
            c2 = candidates_map.get(m.get('candidate2'))
            n1 = '已移除' if m.get('candidate1') else '轮空'
            n2 = '已移除' if m.get('candidate2') else '轮空'
            v1 = v2 = '?'
            if c1 and c2:
                v1 = get_knockout_votes(contest, c1.id, gender, sub_round)
                v2 = get_knockout_votes(contest, c2.id, gender, sub_round)
            banned_mark = ""
            if (c1 and c1.banned) or (c2 and c2.banned):
                banned_mark = "（有角色禁赛）"
            lines.append(f"  {c1.name if c1 else n1}({v1}票) vs {c2.name if c2 else n2}({v2}票){banned_mark}")
    return lines


def _build_prediction_prompt(contest: Contest, phase: str) -> Optional[str]:
    """按阶段构建预测 prompt；返回 None 表示无需预测"""
    if phase in ('closed', 'final_result'):
        return None

    lines = [f"赛事：{contest.title}"]

    if phase in ('not_started', 'nomination', 'review'):
        candidate_count = Candidate.query.filter_by(contest_id=contest.id).count()
        lines.append(f"状态：提名/审核阶段，候选池 {candidate_count} 个角色。")
        return f"""
你是萌战预测专家。

当前数据：
{chr(10).join(lines)}

请预测本届赛事男女组的夺冠热门类型（如人气主角、经典角色等）并说明理由。
格式：用 - 开头列出，总共 120-180 字。
"""

    if phase in ('qualifying', 'qualifying_result'):
        female_top = _get_qualifying_top_votes(contest.id, gender='female', limit=10)
        male_top = _get_qualifying_top_votes(contest.id, gender='male', limit=10)
        if female_top:
            lines.append("\n【女组】海选票数前10名：")
            for i, (_, name, votes) in enumerate(female_top, 1):
                lines.append(f"  {i}. {name}：{votes}票")
        if male_top:
            lines.append("\n【男组】海选票数前10名：")
            for i, (_, name, votes) in enumerate(male_top, 1):
                lines.append(f"  {i}. {name}：{votes}票")
        return f"""
你是萌战预测专家。

当前数据：
{chr(10).join(lines)}

请根据海选票数给出以下预测：
1. 最终冠军预测（男女组各一个）
2. 冠军预测理由（2-3点）
3. 可能出现的黑马角色

格式：用 - 开头列出，总共 150-200 字。
"""

    if phase.startswith('group_round'):
        parts = phase.split('_')
        try:
            round_num = int(parts[2])
        except (IndexError, ValueError):
            round_num = 1
        data = _auto_group_extra_data(contest, phase)
        has_data = False
        for gender, label in (('female', '【女组】'), ('male', '【男组】')):
            section_lines = _group_section_lines(data.get(gender) or {}, round_num)
            if section_lines:
                has_data = True
                lines.append(f"\n{label}")
                lines.extend(section_lines)
        if not has_data:
            return None
        return f"""
你是萌战预测专家。

当前数据（小组赛第{round_num}轮）：
{chr(10).join(lines)}

请根据小组赛积分与对局给出以下预测：
1. 各组最可能出线的角色（提到名字）
2. 积分落后但可能翻盘的黑马
3. 目前看好的最终冠军（男女组各一个）

格式：用 - 开头列出，总共 150-200 字。
"""

    if phase.startswith('knockout_') or phase == 'final_vote':
        knockout_lines = _prediction_knockout_lines(contest)
        if not knockout_lines:
            return None
        lines.extend(knockout_lines)
        return f"""
你是萌战预测专家。

当前数据：
{chr(10).join(lines)}

请根据淘汰赛对阵与实时票数给出以下预测：
1. 本轮最可能晋级的角色（提到名字和理由）
2. 预测的决赛对阵
3. 最终冠军预测（男女组各一个）

格式：用 - 开头列出，总共 150-200 字。
"""

    return None


def generate_prediction(contest_id: int) -> tuple:
    """生成赛事预测（按当前阶段取真实数据：海选/小组赛/淘汰赛各有视角）"""
    try:
        contest = db.session.get(Contest, contest_id)
        if not contest:
            return False, None, "赛事不存在"

        if contest.status == 'draft':
            return True, "赛事尚未开始，AI 预测将在比赛启动后开启。请于 10 月 1 日 18:00 后回来查看！", None

        # 阶段决定数据视角与缓存键。旧实现缓存键只用 status（小组赛15天/淘汰赛
        # 一个键）、数据写死海选票数，导致小组赛和淘汰赛期间预测永远停留在海选视角
        from .public import _calc_current_phase
        phase = _calc_current_phase(contest)

        cache_key = _get_cache_key(contest_id, phase, 'prediction')
        cached = _get_cached(cache_key)
        if cached:
            return True, cached, None

        prompt = _build_prediction_prompt(contest, phase)
        if prompt is None:
            return True, "当前阶段暂无可供预测的数据，请稍后再看。", None

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
        logger.error("AI 预测生成失败: %s", e, exc_info=True)
        return False, None, str(e)
