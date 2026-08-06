"""
南平一中动漫社官网 · 萌战系统引擎
====================================

本模块是萌战系统的核心逻辑层，负责所有与赛事相关的计算和状态变更。
它不处理 HTTP 请求，只处理数据和业务逻辑。

核心功能：
1. 阶段计算 —— 根据当前时间和赛事状态判断所处阶段
2. 时间计算 —— 计算所有赛程节点的时间
3. 赛程推进 —— 海选→小组赛→淘汰赛的自动晋级
4. 数据准备 —— 小组赛公示期、淘汰赛对阵等
5. 排名计算 —— 最终排名生成

使用方式：
    from .contest_engine import calc_phase, run_qualifying_promotion, ...

    phase = calc_phase(contest, now, times)
    run_qualifying_promotion(contest)
"""

import random
from datetime import timedelta

from sqlalchemy import func as sa_func
from sqlalchemy.orm.attributes import flag_modified

from .models import db, Candidate, ContestVote


# ============================================================
# 时间计算
# ============================================================

def calc_stage_times(open_at):
    """
    根据开始时间计算所有赛程节点时间
    返回一个对象，包含所有阶段的截止时间
    """

    def set_time_to_18(dt):
        result = dt.replace(hour=18, minute=0, second=0, microsecond=0)
        # 如果被拽回之前的时间，自动加一天
        if result < dt:
            result += timedelta(days=1)
        return result

    if not open_at:
        return {
            'nomination_end': None,
            'review_end': None,
            'qualifying_vote_end': None,
            'qualifying_end': None,
            'group_round_1_end': None,
            'group_round_1_result_end': None,
            'group_round_2_end': None,
            'group_round_2_result_end': None,
            'group_round_3_end': None,
            'group_round_3_result_end': None,
            'knockout_16_end': None,
            'knockout_16_result_end': None,
            'knockout_8_end': None,
            'knockout_8_result_end': None,
            'knockout_4_end': None,
            'knockout_4_result_end': None,
            'final_vote_end': None,
            'final_result_end': None,
        }

    return {
        'nomination_end': set_time_to_18(open_at + timedelta(days=5)),
        'review_end': set_time_to_18(open_at + timedelta(days=8)),
        'qualifying_vote_end': set_time_to_18(open_at + timedelta(days=12)),
        'qualifying_end': set_time_to_18(open_at + timedelta(days=13)),
        'group_round_1_end': set_time_to_18(open_at + timedelta(days=17)),
        'group_round_1_result_end': set_time_to_18(open_at + timedelta(days=18)),
        'group_round_2_end': set_time_to_18(open_at + timedelta(days=22)),
        'group_round_2_result_end': set_time_to_18(open_at + timedelta(days=23)),
        'group_round_3_end': set_time_to_18(open_at + timedelta(days=27)),
        'group_round_3_result_end': set_time_to_18(open_at + timedelta(days=28)),
        'knockout_16_end': set_time_to_18(open_at + timedelta(days=32)),
        'knockout_16_result_end': set_time_to_18(open_at + timedelta(days=33)),
        'knockout_8_end': set_time_to_18(open_at + timedelta(days=37)),
        'knockout_8_result_end': set_time_to_18(open_at + timedelta(days=38)),
        'knockout_4_end': set_time_to_18(open_at + timedelta(days=42)),
        'knockout_4_result_end': set_time_to_18(open_at + timedelta(days=43)),
        'final_vote_end': set_time_to_18(open_at + timedelta(days=47)),
        'final_result_end': set_time_to_18(open_at + timedelta(days=50)),
    }


# ============================================================
# 阶段判断
# ============================================================

def calc_phase(contest, now, times):
    """
    根据赛事状态和当前时间判断所处阶段
    返回 phase 字符串
    """
    # 如果赛事已关闭
    if contest.status == 'closed':
        return 'closed'

    # 如果赛事是草稿
    if contest.status == 'draft':
        return 'not_started'

    # 小组赛阶段
    if contest.status == 'group_stage':
        if now <= times['group_round_1_end']:
            return 'group_round_1'
        elif now <= times['group_round_1_result_end']:
            return 'group_round_1_result'
        elif now <= times['group_round_2_end']:
            return 'group_round_2'
        elif now <= times['group_round_2_result_end']:
            return 'group_round_2_result'
        elif now <= times['group_round_3_end']:
            return 'group_round_3'
        elif now <= times['group_round_3_result_end']:
            return 'group_round_3_result'
        else:
            return 'group_round_3_result'

    # 淘汰赛阶段
    if contest.status == 'knockout':
        if now <= times['knockout_16_end']:
            return 'knockout_16'
        elif now <= times['knockout_16_result_end']:
            return 'knockout_16_result'
        elif now <= times['knockout_8_end']:
            return 'knockout_8'
        elif now <= times['knockout_8_result_end']:
            return 'knockout_8_result'
        elif now <= times['knockout_4_end']:
            return 'knockout_4'
        elif now <= times['knockout_4_result_end']:
            return 'knockout_4_result'
        elif now <= times['final_vote_end']:
            return 'final_vote'
        elif now <= times['final_result_end']:
            return 'final_result'
        else:
            if contest.status != 'closed':
                contest.status = 'closed'
                db.session.commit()
            return 'closed'

    # open 状态按时间判断
    open_at = contest.open_at
    if not open_at:
        return 'not_started'

    if now < open_at:
        return 'not_started'
    elif now <= times['nomination_end']:
        return 'nomination'
    elif now <= times['review_end']:
        return 'review'
    elif now <= times['qualifying_vote_end']:
        return 'qualifying'
    elif now <= times['qualifying_end']:
        return 'qualifying_result'
    elif now <= times['group_round_1_end']:
        return 'group_round_1'
    elif now <= times['group_round_1_result_end']:
        return 'group_round_1_result'
    elif now <= times['group_round_2_end']:
        return 'group_round_2'
    elif now <= times['group_round_2_result_end']:
        return 'group_round_2_result'
    elif now <= times['group_round_3_end']:
        return 'group_round_3'
    elif now <= times['group_round_3_result_end']:
        return 'group_round_3_result'
    elif now <= times['knockout_16_end']:
        return 'knockout_16'
    elif now <= times['knockout_16_result_end']:
        return 'knockout_16_result'
    elif now <= times['knockout_8_end']:
        return 'knockout_8'
    elif now <= times['knockout_8_result_end']:
        return 'knockout_8_result'
    elif now <= times['knockout_4_end']:
        return 'knockout_4'
    elif now <= times['knockout_4_result_end']:
        return 'knockout_4_result'
    elif now <= times['final_vote_end']:
        return 'final_vote'
    elif now <= times['final_result_end']:
        return 'final_result'
    else:
        if contest.status != 'closed':
            contest.status = 'closed'
            db.session.commit()
        return 'closed'


# ============================================================
# 自动激活
# ============================================================

def auto_activate_contest(contest, now):
    """草稿赛事在到达开始时间后自动激活"""
    if contest.status == 'draft' and contest.open_at:
        # 确保 open_at 是 naive（去掉时区）
        open_at = contest.open_at
        if open_at.tzinfo is not None:
            open_at = open_at.replace(tzinfo=None)
        # now 应该已是 naive，但为了安全也处理
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        if now >= open_at:
            contest.status = 'open'
            db.session.commit()
            return True
    return False


# ============================================================
# 海选晋级 → 小组赛
# ============================================================

def run_qualifying_promotion(contest):
    """海选公示结束后，前32名晋级小组赛并随机分组"""
    if contest.config is None:
        contest.config = {}

    female_candidates = contest.candidates.filter_by(gender='female').all()
    male_candidates = contest.candidates.filter_by(gender='male').all()

    def count_votes(candidates):
        result = []
        for c in candidates:
            total = ContestVote.query.filter_by(
                candidate_id=c.id, round_number=0
            ).with_entities(sa_func.sum(ContestVote.weight)).scalar() or 0
            result.append({'candidate': c, 'total_votes': total})
        result.sort(key=lambda x: x['total_votes'], reverse=True)
        return result

    female_result = count_votes(female_candidates)
    male_result = count_votes(male_candidates)

    female_top32 = [item['candidate'] for item in female_result[:32]]
    male_top32 = [item['candidate'] for item in male_result[:32]]

    for c in female_top32:
        c.stage = 'group_stage'
    for c in male_top32:
        c.stage = 'group_stage'

    def generate_groups(candidates, group_count=8):
        random.shuffle(candidates)
        groups = []
        for i in range(group_count):
            groups.append(candidates[i * 4:(i + 1) * 4])
        return groups

    female_groups = generate_groups(female_top32)
    male_groups = generate_groups(male_top32)

    contest.config['female_groups'] = [[c.id for c in group] for group in female_groups]
    contest.config['male_groups'] = [[c.id for c in group] for group in male_groups]
    contest.config['female_top32'] = [c.id for c in female_top32]
    contest.config['male_top32'] = [c.id for c in male_top32]

    # 保存海选结果时加入 candidate.id，用于平票决胜
    contest.config['female_result'] = [
        {'id': item['candidate'].id,
         'name': item['candidate'].name,
         'source': item['candidate'].source,
         'votes': item['total_votes'],
         'image_url': item['candidate'].image_url}
        for item in female_result[:32]
    ]
    contest.config['male_result'] = [
        {'id': item['candidate'].id,
         'name': item['candidate'].name,
         'source': item['candidate'].source,
         'votes': item['total_votes'],
         'image_url': item['candidate'].image_url}
        for item in male_result[:32]
    ]

    # 显式标记 config 字段已修改
    flag_modified(contest, 'config')

    contest.status = 'group_stage'
    db.session.commit()


# ============================================================
# 小组赛晋级 → 淘汰赛
# ============================================================

def run_group_promotion(contest, session=None):
    """小组赛第3轮公示结束后，每组前2晋级淘汰赛，生成16强对阵"""
    if session is None:
        session = db.session

    if contest.config is None:
        contest.config = {}

    def get_group_stage_results(gender):
        candidates = session.query(Candidate).filter_by(
            contest_id=contest.id,
            gender=gender,
            stage='group_stage'
        ).all()
        if not candidates:
            return [], {}

        groups = contest.config.get(f'{gender}_groups', [])
        if not groups:
            return [], {}

        result = {}
        for c in candidates:
            result[c.id] = {
                'name': c.name,
                'candidate': c,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'points': 0,
                'total_votes': 0,
                'group_index': None
            }

        for gi, group in enumerate(groups):
            for cid in group:
                if cid in result:
                    result[cid]['group_index'] = gi

        for gi, group in enumerate(groups):
            group_candidates = [cid for cid in group if cid in result]
            if len(group_candidates) < 4:
                continue

            for round_num in [1, 2, 3]:
                if round_num == 1:
                    pairs = [(group_candidates[0], group_candidates[1]),
                             (group_candidates[2], group_candidates[3])]
                elif round_num == 2:
                    pairs = [(group_candidates[0], group_candidates[2]),
                             (group_candidates[1], group_candidates[3])]
                else:
                    pairs = [(group_candidates[0], group_candidates[3]),
                             (group_candidates[1], group_candidates[2])]

                for cid1, cid2 in pairs:
                    votes1 = session.query(
                        sa_func.sum(ContestVote.weight)
                    ).filter(
                        ContestVote.contest_id == contest.id,
                        ContestVote.candidate_id == cid1,
                        ContestVote.round_number == round_num,
                        ContestVote.gender == gender
                    ).scalar() or 0

                    votes2 = session.query(
                        sa_func.sum(ContestVote.weight)
                    ).filter(
                        ContestVote.contest_id == contest.id,
                        ContestVote.candidate_id == cid2,
                        ContestVote.round_number == round_num,
                        ContestVote.gender == gender
                    ).scalar() or 0

                    result[cid1]['total_votes'] += votes1
                    result[cid2]['total_votes'] += votes2

                    if votes1 > votes2:
                        result[cid1]['wins'] += 1
                        result[cid2]['losses'] += 1
                    elif votes1 < votes2:
                        result[cid2]['wins'] += 1
                        result[cid1]['losses'] += 1
                    else:
                        result[cid1]['draws'] += 1
                        result[cid2]['draws'] += 1

        for cid, data in result.items():
            data['points'] = data['wins'] * 3 + data['draws'] * 1

        return result, groups

    def get_top2_from_groups(result, groups):
        """
        返回 (top16_ids, top16_info)
        top16_ids: [id, ...]  -- 便于兼容原调用处
        top16_info: [{'id': id, 'group_index': gi, 'rank': 1_or_2}, ...]
        同时会把晋级者的 candidate.stage 标记为 'knockout'
        """
        top16 = []
        top16_info = []
        for gi, group in enumerate(groups):
            group_candidates = [cid for cid in group if cid in result]
            # 对每组按 (points, total_votes) 排序
            group_candidates.sort(key=lambda cid: (result[cid]['points'], result[cid]['total_votes']), reverse=True)
            top2 = group_candidates[:2]
            # top2 可能少于 2，按实际情况处理
            for rank, cid in enumerate(top2, start=1):
                top16.append(cid)
                top16_info.append({'id': cid, 'group_index': gi, 'rank': rank})
                if cid in result:
                    result[cid]['candidate'].stage = 'knockout'
        return top16, top16_info

    def generate_knockout_matches(candidate_inputs):
        """
        支持两种格式：
        - 旧格式: list of ids (int) -> 随机配对（向后兼容）
        - 新格式: list of dicts [{'id':..., 'group_index':..., 'rank':1|2}, ...]
        优先规则：小组第一 vs 小组第二，且回避同组（无可用对手时回退）
        """
        if not candidate_inputs:
            return []

        # 旧格式兼容：纯 ID 列表 -> 随机配对
        if isinstance(candidate_inputs[0], (int, str)):
            shuffled = list(candidate_inputs)
            random.shuffle(shuffled)
            matches = []
            for i in range(0, len(shuffled), 2):
                if i + 1 < len(shuffled):
                    matches.append({
                        'round': 'round_1',
                        'round_name': '16强',
                        'candidate1': shuffled[i],
                        'candidate2': shuffled[i + 1],
                        'status': 'active',
                        'votes1': 0,
                        'votes2': 0,
                        'winner': None
                    })
            return matches

        # 新格式：info 列表 -> 第一对第二 + 同组回避
        infos = list(candidate_inputs)
        winners = [i for i in infos if i.get('rank') == 1]
        runners = [i for i in infos if i.get('rank') == 2]

        # 如果数量不对，回退到随机配对
        if len(winners) + len(runners) < 16:
            ids = [i.get('id') for i in infos]
            shuffled = ids[:]
            random.shuffle(shuffled)
            matches = []
            for i in range(0, len(shuffled), 2):
                if i + 1 < len(shuffled):
                    matches.append({
                        'round': 'round_1',
                        'round_name': '16强',
                        'candidate1': shuffled[i],
                        'candidate2': shuffled[i + 1],
                        'status': 'active',
                        'votes1': 0,
                        'votes2': 0,
                        'winner': None
                    })
            return matches

        random.shuffle(winners)
        random.shuffle(runners)

        matches = []
        remaining_runners = runners[:]
        for w in winners:
            # 找一个不同组的 runner
            pick_idx = None
            for idx, r in enumerate(remaining_runners):
                if r.get('group_index') != w.get('group_index'):
                    pick_idx = idx
                    break
            # 回退：如果没有不同组的，取第一个
            if pick_idx is None:
                pick = remaining_runners.pop(0)
            else:
                pick = remaining_runners.pop(pick_idx)

            matches.append({
                'round': 'round_1',
                'round_name': '16强',
                'candidate1': w.get('id'),
                'candidate2': pick.get('id'),
                'status': 'active',
                'votes1': 0,
                'votes2': 0,
                'winner': None
            })

        # 剩余未配对的 runner 不会发生（因为 winners == runners == 8）
        return matches

    female_result, female_groups = get_group_stage_results('female')
    male_result, male_groups = get_group_stage_results('male')

    female_top16, female_top16_info = get_top2_from_groups(female_result, female_groups)
    male_top16, male_top16_info = get_top2_from_groups(male_result, male_groups)

    female_matches = generate_knockout_matches(female_top16_info)
    male_matches = generate_knockout_matches(male_top16_info)

    contest.config['knockout_matches_female'] = female_matches
    contest.config['knockout_matches_male'] = male_matches
    contest.config['female_top16'] = female_top16
    contest.config['male_top16'] = male_top16
    contest.config['female_top16_info'] = female_top16_info
    contest.config['male_top16_info'] = male_top16_info

    for cid in female_top16:
        candidate = session.get(Candidate, cid)
        if candidate:
            candidate.stage = 'knockout'
    for cid in male_top16:
        candidate = session.get(Candidate, cid)
        if candidate:
            candidate.stage = 'knockout'

    # ====== 生产环境防护：防止空数据推进 ======
    if contest.config.get('female_groups') and len(female_top16) < 16:
        raise ValueError(
            f"女子组晋级人数异常: 需要16人，实际 {len(female_top16)} 人。"
            f"请检查小组赛投票数据是否完整。"
        )
    if contest.config.get('male_groups') and len(male_top16) < 16:
        raise ValueError(
            f"男子组晋级人数异常: 需要16人，实际 {len(male_top16)} 人。"
            f"请检查小组赛投票数据是否完整。"
        )

    contest.status = 'knockout'
    session.commit()
    # ==========================================


# ============================================================
# 淘汰赛辅助函数
# ============================================================

def get_knockout_votes(contest, candidate_id, gender, sub_round):
    """统计单个候选人在淘汰赛本轮的总票数"""
    total = ContestVote.query.filter_by(
        contest_id=contest.id,
        candidate_id=candidate_id,
        round_number=4,
        sub_round=sub_round,
        gender=gender
    ).with_entities(db.func.sum(ContestVote.weight)).scalar() or 0
    return total


def get_match_winner(contest, match, gender, sub_round):
    """确定一场比赛的胜者（票数高者，平票则比较海选总票数）"""
    c1_votes = get_knockout_votes(contest, match['candidate1'], gender, sub_round)
    c2_votes = get_knockout_votes(contest, match['candidate2'], gender, sub_round)

    if c1_votes > c2_votes:
        return match['candidate1']
    elif c2_votes > c1_votes:
        return match['candidate2']

    # 平票，比较海选票数（用 candidate.id 匹配，避免重名问题）
    if gender == 'female':
        results = contest.config.get('female_result', [])
    else:
        results = contest.config.get('male_result', [])

    c1_id = match['candidate1']
    c2_id = match['candidate2']

    c1_qualifying = next((item['votes'] for item in results if item.get('id') == c1_id), 0)
    c2_qualifying = next((item['votes'] for item in results if item.get('id') == c2_id), 0)

    return match['candidate1'] if c1_qualifying >= c2_qualifying else match['candidate2']


def generate_next_round(contest, matches, gender, sub_round, round_name):
    """根据上一轮胜者生成下一轮对阵"""
    winners = []
    for match in matches:
        winner_id = get_match_winner(contest, match, gender, sub_round)
        match['winner'] = winner_id
        match['status'] = 'finished'
        winners.append(winner_id)

    random.shuffle(winners)
    next_matches = []
    for i in range(0, len(winners), 2):
        if i + 1 < len(winners):
            next_matches.append({
                'round': round_name,
                'round_name': round_name,
                'candidate1': winners[i],
                'candidate2': winners[i + 1],
                'status': 'active',
                'votes1': 0,
                'votes2': 0,
                'winner': None
            })
    return next_matches


# ============================================================
# 淘汰赛推进
# ============================================================

def run_knockout_advance(contest, phase, now, times):
    """
    淘汰赛各轮自动推进
    返回: (是否已推进, 推进后的轮次名称或None)
    """
    if phase == 'knockout_16_result' and now >= times['knockout_16_result_end'] and contest.status == 'knockout':
        female_matches = contest.config.get('knockout_matches_female', [])
        male_matches = contest.config.get('knockout_matches_male', [])
        if female_matches:
            contest.config['knockout_matches_female'] = generate_next_round(contest, female_matches, 'female', 1, '8强')
        if male_matches:
            contest.config['knockout_matches_male'] = generate_next_round(contest, male_matches, 'male', 1, '8强')
        flag_modified(contest, 'config')
        db.session.commit()
        return True, '8强'

    elif phase == 'knockout_8_result' and now >= times['knockout_8_result_end'] and contest.status == 'knockout':
        female_matches = contest.config.get('knockout_matches_female', [])
        male_matches = contest.config.get('knockout_matches_male', [])
        if female_matches:
            contest.config['knockout_matches_female'] = generate_next_round(contest, female_matches, 'female', 2, '4强')
        if male_matches:
            contest.config['knockout_matches_male'] = generate_next_round(contest, male_matches, 'male', 2, '4强')
        flag_modified(contest, 'config')
        db.session.commit()
        return True, '4强'

    elif phase == 'knockout_4_result' and now >= times['knockout_4_result_end'] and contest.status == 'knockout':
        female_matches = contest.config.get('knockout_matches_female', [])
        male_matches = contest.config.get('knockout_matches_male', [])
        if female_matches:
            contest.config['knockout_matches_female'] = generate_next_round(contest, female_matches, 'female', 3,
                                                                            '决赛')
        if male_matches:
            contest.config['knockout_matches_male'] = generate_next_round(contest, male_matches, 'male', 3, '决赛')
        flag_modified(contest, 'config')
        db.session.commit()
        return True, '决赛'

    return False, None


# ============================================================
# 最终排名
# ============================================================

def run_final_ranking(contest):
    """决赛结束后生成最终排名并标记冠军"""
    if contest.config is None:
        contest.config = {}

    female_candidates = contest.candidates.filter_by(gender='female').filter(
        Candidate.stage.in_(['knockout', 'champion'])).all()
    male_candidates = contest.candidates.filter_by(gender='male').filter(
        Candidate.stage.in_(['knockout', 'champion'])).all()

    def get_final_ranking(candidates, gender):
        """按淘汰轮次排序生成排名"""
        matches_16 = contest.config.get('knockout_matches_female' if gender == 'female' else 'knockout_matches_male',
                                        [])
        if not matches_16:
            return []

        matches_8 = contest.config.get('knockout_matches_female' if gender == 'female' else 'knockout_matches_male', [])
        if not matches_8:
            matches_8 = []
        matches_4 = contest.config.get('knockout_matches_female' if gender == 'female' else 'knockout_matches_male', [])
        if not matches_4:
            matches_4 = []
        matches_final = contest.config.get('knockout_matches_female' if gender == 'female' else 'knockout_matches_male',
                                           [])
        if not matches_final:
            matches_final = []

        ranking = []

        # 1. 决赛
        final_match = None
        if matches_final and len(matches_final) > 0:
            final_match = matches_final[-1]
            if final_match.get('winner'):
                winner = db.session.get(Candidate, final_match['winner'])
                if winner:
                    ranking.append({
                        'candidate': winner,
                        'stage': 'champion',
                        'votes': get_knockout_votes(contest, winner.id, gender, 4)
                    })
                loser_id = final_match['candidate1'] if final_match['winner'] == final_match['candidate2'] else \
                    final_match['candidate2']
                loser = db.session.get(Candidate, loser_id)
                if loser:
                    ranking.append({
                        'candidate': loser,
                        'stage': 'finalist',
                        'votes': get_knockout_votes(contest, loser.id, gender, 4)
                    })

        # 2. 4强
        if matches_4 and len(matches_4) >= 2:
            for match in matches_4[:2]:
                loser_id = match['candidate1'] if match['winner'] == match['candidate2'] else match['candidate2']
                loser = db.session.get(Candidate, loser_id)
                if loser:
                    ranking.append({
                        'candidate': loser,
                        'stage': 'semifinalist',
                        'votes': get_knockout_votes(contest, loser.id, gender, 3)
                    })

        # 3. 8强
        if matches_8 and len(matches_8) >= 4:
            for match in matches_8[:4]:
                loser_id = match['candidate1'] if match['winner'] == match['candidate2'] else match['candidate2']
                loser = db.session.get(Candidate, loser_id)
                if loser:
                    ranking.append({
                        'candidate': loser,
                        'stage': 'quarterfinalist',
                        'votes': get_knockout_votes(contest, loser.id, gender, 2)
                    })

        # 4. 16强
        if matches_16 and len(matches_16) >= 8:
            for match in matches_16[:8]:
                loser_id = match['candidate1'] if match['winner'] == match['candidate2'] else match['candidate2']
                loser = db.session.get(Candidate, loser_id)
                if loser:
                    ranking.append({
                        'candidate': loser,
                        'stage': 'round16',
                        'votes': get_knockout_votes(contest, loser.id, gender, 1)
                    })

        stage_order = {
            'champion': 0,
            'finalist': 1,
            'semifinalist': 2,
            'quarterfinalist': 3,
            'round16': 4
        }
        ranking.sort(key=lambda x: (stage_order.get(x['stage'], 99), -x['votes']))

        result = []
        for item in ranking:
            result.append({
                'name': item['candidate'].name,
                'source': item['candidate'].source,
                'votes': item['votes'],
                'stage': item['stage']
            })
        return result

    contest.config['female_ranking'] = get_final_ranking(female_candidates, 'female')
    contest.config['male_ranking'] = get_final_ranking(male_candidates, 'male')

    # 强制标记 config 已修改
    flag_modified(contest, 'config')

    # 标记冠军和亚军（从排名列表中取前两名）
    if contest.config['female_ranking']:
        # 冠军
        champion_name = contest.config['female_ranking'][0]['name']
        champion = Candidate.query.filter_by(contest_id=contest.id, name=champion_name).first()
        if champion:
            champion.stage = 'champion'
        # 亚军（如果有）
        if len(contest.config['female_ranking']) >= 2:
            runner_name = contest.config['female_ranking'][1]['name']
            runner = Candidate.query.filter_by(contest_id=contest.id, name=runner_name).first()
            if runner:
                runner.stage = 'finalist'

    if contest.config['male_ranking']:
        champion_name = contest.config['male_ranking'][0]['name']
        champion = Candidate.query.filter_by(contest_id=contest.id, name=champion_name).first()
        if champion:
            champion.stage = 'champion'
        if len(contest.config['male_ranking']) >= 2:
            runner_name = contest.config['male_ranking'][1]['name']
            runner = Candidate.query.filter_by(contest_id=contest.id, name=runner_name).first()
            if runner:
                runner.stage = 'finalist'

    contest.status = 'closed'
    db.session.commit()


# ============================================================
# 小组赛公示数据准备
# ============================================================

def prepare_group_round_data(contest, phase):
    """
    准备小组赛公示期数据
    返回: (group_round_results, overall_ranking_female, overall_ranking_male)
    """
    if phase not in ['group_round_1_result', 'group_round_2_result', 'group_round_3_result']:
        return None, None, None

    # 修复：正确解析轮次数字（原代码 phase.split('_')[1] 会取到 'round'）
    parts = phase.split('_')
    try:
        round_num = int(parts[2])  # 'group_round_1_result' -> 1
    except (IndexError, ValueError):
        raise ValueError(f"无法解析小组轮次: {phase}")

    groups_female = contest.config.get('female_groups', [])
    groups_male = contest.config.get('male_groups', [])
    candidates_map = {c.id: c for c in contest.candidates.all()}

    def get_group_matches(gender, groups):
        if not groups:
            return []
        result = []
        for gi, group in enumerate(groups):
            group_name = chr(65 + gi) + '组'
            if round_num == 1:
                pairs = [(group[0], group[1]), (group[2], group[3])]
            elif round_num == 2:
                pairs = [(group[0], group[2]), (group[1], group[3])]
            else:
                pairs = [(group[0], group[3]), (group[1], group[2])]

            matches = []
            for cid1, cid2 in pairs:
                c1 = candidates_map.get(cid1)
                c2 = candidates_map.get(cid2)
                if not c1 or not c2:
                    continue
                votes1 = ContestVote.query.filter_by(
                    contest_id=contest.id, candidate_id=cid1,
                    round_number=round_num, gender=gender
                ).with_entities(sa_func.sum(ContestVote.weight)).scalar() or 0
                votes2 = ContestVote.query.filter_by(
                    contest_id=contest.id, candidate_id=cid2,
                    round_number=round_num, gender=gender
                ).with_entities(sa_func.sum(ContestVote.weight)).scalar() or 0
                winner = cid1 if votes1 > votes2 else (cid2 if votes2 > votes1 else None)
                matches.append({
                    'candidate1': c1,
                    'candidate2': c2,
                    'votes1': votes1,
                    'votes2': votes2,
                    'winner': winner
                })
            result.append({'group_name': group_name, 'matches': matches})
        return result

    def get_overall_ranking(gender, groups):
        candidates = db.session.query(Candidate).filter_by(
            contest_id=contest.id,
            gender=gender,
            stage='group_stage'
        ).all()
        if not candidates:
            return []

        group_map = {}
        for gi, group in enumerate(groups):
            for cid in group:
                group_map[cid] = chr(65 + gi) + '组'

        stats = {}
        for c in candidates:
            stats[c.id] = {
                'name': c.name,
                'image_url': c.image_url,
                'group': group_map.get(c.id, ''),
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'points': 0,
            }

        for r in range(1, round_num + 1):
            for gi, group in enumerate(groups):
                group_candidates = [cid for cid in group if cid in stats]
                if len(group_candidates) < 4:
                    continue
                if r == 1:
                    pairs = [(group_candidates[0], group_candidates[1]),
                             (group_candidates[2], group_candidates[3])]
                elif r == 2:
                    pairs = [(group_candidates[0], group_candidates[2]),
                             (group_candidates[1], group_candidates[3])]
                else:
                    pairs = [(group_candidates[0], group_candidates[3]),
                             (group_candidates[1], group_candidates[2])]

                for cid1, cid2 in pairs:
                    votes1 = ContestVote.query.filter_by(
                        contest_id=contest.id, candidate_id=cid1,
                        round_number=r, gender=gender
                    ).with_entities(sa_func.sum(ContestVote.weight)).scalar() or 0
                    votes2 = ContestVote.query.filter_by(
                        contest_id=contest.id, candidate_id=cid2,
                        round_number=r, gender=gender
                    ).with_entities(sa_func.sum(ContestVote.weight)).scalar() or 0

                    if votes1 > votes2:
                        stats[cid1]['wins'] += 1
                        stats[cid2]['losses'] += 1
                    elif votes1 < votes2:
                        stats[cid2]['wins'] += 1
                        stats[cid1]['losses'] += 1
                    else:
                        stats[cid1]['draws'] += 1
                        stats[cid2]['draws'] += 1

        for cid, data in stats.items():
            data['points'] = data['wins'] * 3 + data['draws'] * 1

        return sorted(stats.values(), key=lambda x: x['points'], reverse=True)

    group_round_results = {
        'female': get_group_matches('female', groups_female),
        'male': get_group_matches('male', groups_male)
    }

    overall_ranking_female = get_overall_ranking('female', groups_female)
    overall_ranking_male = get_overall_ranking('male', groups_male)

    return group_round_results, overall_ranking_female, overall_ranking_male
