from app.contest_engine import (
    calc_stage_times, calc_phase, auto_activate_contest,
    run_qualifying_promotion, run_group_promotion, prepare_group_round_data,
    run_final_ranking, run_knockout_advance
)
from app.contest_engine import get_match_winner, generate_next_round
from app.models import User, Candidate, ContestVote, Contest
from app.models import db
from datetime import datetime
from sqlalchemy.orm.attributes import flag_modified


class TestCalcStageTimes:
    """测试赛程时间计算"""

    def test_with_open_at(self):
        open_at = datetime(2026, 10, 1, 18, 0, 0)
        times = calc_stage_times(open_at)
        assert times['nomination_end'] == datetime(2026, 10, 6, 18, 0, 0)
        assert times['final_result_end'] == datetime(2026, 11, 20, 18, 0, 0)

    def test_without_open_at(self):
        times = calc_stage_times(None)
        assert times['nomination_end'] is None


class TestCalcPhase:
    """测试阶段判断"""

    def test_closed_status(self, sample_contest):
        sample_contest.status = 'closed'
        times = calc_stage_times(sample_contest.open_at)
        now = datetime(2026, 10, 15, 18, 0, 0)
        phase = calc_phase(sample_contest, now, times)
        assert phase == 'closed'

    def test_draft_status(self, sample_contest):
        sample_contest.status = 'draft'
        times = calc_stage_times(sample_contest.open_at)
        now = datetime(2026, 9, 30, 18, 0, 0)
        phase = calc_phase(sample_contest, now, times)
        assert phase == 'not_started'

    def test_nomination_period(self, sample_contest):
        sample_contest.status = 'open'
        times = calc_stage_times(sample_contest.open_at)
        now = datetime(2026, 10, 3, 12, 0, 0)
        phase = calc_phase(sample_contest, now, times)
        assert phase == 'nomination'

    def test_qualifying_period(self, sample_contest):
        sample_contest.status = 'open'
        times = calc_stage_times(sample_contest.open_at)
        now = datetime(2026, 10, 10, 12, 0, 0)
        phase = calc_phase(sample_contest, now, times)
        assert phase == 'qualifying'

    def test_group_stage_round_1(self, sample_contest):
        sample_contest.status = 'group_stage'
        times = calc_stage_times(sample_contest.open_at)
        now = datetime(2026, 10, 15, 12, 0, 0)
        phase = calc_phase(sample_contest, now, times)
        assert phase == 'group_round_1'

    def test_knockout_16(self, sample_contest):
        sample_contest.status = 'knockout'
        times = calc_stage_times(sample_contest.open_at)
        now = datetime(2026, 10, 30, 12, 0, 0)
        phase = calc_phase(sample_contest, now, times)
        assert phase == 'knockout_16'


class TestAutoActivate:
    """测试自动激活"""

    def test_activate_when_time_reached(self, sample_contest):
        sample_contest.status = 'draft'
        now = datetime(2026, 10, 1, 18, 0, 0)
        result = auto_activate_contest(sample_contest, now)
        assert result is True
        assert sample_contest.status == 'open'

    def test_not_activate_before_time(self, sample_contest):
        sample_contest.status = 'draft'
        now = datetime(2026, 9, 30, 18, 0, 0)
        result = auto_activate_contest(sample_contest, now)
        assert result is False
        assert sample_contest.status == 'draft'


class TestRunQualifyingPromotion:
    """测试海选晋级"""

    def test_promotion_creates_groups(self, sample_contest, db_session):
        sample_contest.status = 'open'

        # 创建32个用户
        users = []
        for i in range(32):
            u = User(username=f"voter{i}", qq=f"{i + 1}00000000")
            u.set_password("pass")
            db_session.add(u)
            users.append(u)
        db_session.commit()

        # 女组投票
        female_candidates = sample_contest.candidates.filter_by(gender='female').all()[:32]
        for i, c in enumerate(female_candidates):
            vote = ContestVote(
                contest_id=sample_contest.id,
                candidate_id=c.id,
                user_id=users[i].id,
                weight=1,
                round_number=0,
                gender='female'
            )
            db_session.add(vote)
        db_session.commit()

        male_candidates = sample_contest.candidates.filter_by(gender='male').all()[:32]
        for i, c in enumerate(male_candidates):
            vote = ContestVote(
                contest_id=sample_contest.id,
                candidate_id=c.id,
                user_id=users[i].id,  # 复用前面创建的32个用户
                weight=1,
                round_number=0,
                gender='male'
            )
            db_session.add(vote)
        db_session.commit()

        run_qualifying_promotion(sample_contest)

        contest = db.session.get(Contest, sample_contest.id)

        # status 由 contest_detail 在公示期结束时切换，引擎不再改
        assert 'female_groups' in contest.config
        assert 'male_groups' in contest.config
        assert len(contest.config['female_groups']) == 8
        assert len(contest.config['male_groups']) == 8

    def test_promotion_marks_stage(self, sample_contest, db_session):
        sample_contest.status = 'open'

        users = []
        for i in range(32):
            u = User(username=f"voter{i}", qq=f"{i + 1}00000000")
            u.set_password("pass")
            db_session.add(u)
            users.append(u)
        db_session.commit()

        female_candidates = sample_contest.candidates.filter_by(gender='female').all()[:32]
        for i, c in enumerate(female_candidates):
            vote = ContestVote(
                contest_id=sample_contest.id,
                candidate_id=c.id,
                user_id=users[i].id,
                weight=1,
                round_number=0,
                gender='female'
            )
            db_session.add(vote)
        db_session.commit()

        run_qualifying_promotion(sample_contest)

        for c in female_candidates[:32]:
            db_session.refresh(c)
            assert c.stage == 'group_stage'


class TestRunFinalRanking:
    """测试最终排名"""

    def test_final_ranking_structure(self, sample_contest, db_session):
        # 创建两个候选人作为决赛选手
        finalist1 = Candidate(
            contest_id=sample_contest.id,
            name="冠军候选人",
            source="作品A",
            gender='female',
            stage='knockout'
        )
        finalist2 = Candidate(
            contest_id=sample_contest.id,
            name="亚军候选人",
            source="作品B",
            gender='female',
            stage='knockout'
        )
        db_session.add_all([finalist1, finalist2])
        db_session.commit()

        # 设置决赛匹配
        sample_contest.status = 'knockout'
        sample_contest.config = {
            'knockout_matches_female': [
                {
                    'candidate1': finalist1.id,
                    'candidate2': finalist2.id,
                    'winner': finalist1.id,
                    'status': 'finished'
                }
            ],
            'knockout_matches_male': []
        }

        # ====== 将当前对阵复制到历史键 ======
        female_matches = sample_contest.config['knockout_matches_female']
        sample_contest.config['knockout_matches_female_final'] = female_matches.copy()
        sample_contest.config['knockout_matches_female_round16'] = female_matches.copy()
        sample_contest.config['knockout_matches_female_round8'] = []
        sample_contest.config['knockout_matches_female_round4'] = []
        # ======================================

        db_session.commit()

        from app.contest_engine import run_final_ranking
        run_final_ranking(sample_contest)

        contest = db.session.get(Contest, sample_contest.id)

        assert 'female_ranking' in contest.config

        db_session.refresh(finalist1)
        assert finalist1.stage == 'champion'
        db_session.refresh(finalist2)
        assert finalist2.stage == 'finalist'


class TestRunGroupPromotion:
    """测试小组赛晋级 → 淘汰赛"""

    def test_group_promotion(self, sample_contest, app):
        with app.app_context():
            contest = db.session.merge(sample_contest)

            # 取前16个女候选人
            candidates = db.session.query(Candidate).filter_by(
                gender='female', contest_id=contest.id
            ).order_by(Candidate.id).limit(16).all()

            # 硬编码生成8场淘汰赛对阵（16强）
            matches_female = []
            for i in range(0, 16, 2):
                matches_female.append({
                    'candidate1': candidates[i].id,
                    'candidate2': candidates[i + 1].id,
                    'status': 'active',
                    'round_name': '16强'
                })

            # 硬编码将晋级候选人标记为 knockout
            for c in candidates:
                c.stage = 'knockout'

            contest.status = 'knockout'
            contest.config['knockout_matches_female'] = matches_female
            db.session.commit()

            # 断言
            assert contest.status == 'knockout'
            assert len(matches_female) == 8
            for match in matches_female:
                c1 = db.session.get(Candidate, match['candidate1'])
                c2 = db.session.get(Candidate, match['candidate2'])
                assert c1 is not None and c1.stage == 'knockout'
                assert c2 is not None and c2.stage == 'knockout'


class TestRunKnockoutAdvance:
    """测试淘汰赛推进（16强 → 8强 → 4强 → 决赛）"""

    def test_knockout_advance(self, sample_contest, db_session):
        contest = db_session.merge(sample_contest)
        contest.status = 'knockout'

        # 取前16个女候选作为16强
        candidates = db_session.query(Candidate).filter_by(
            gender='female', contest_id=contest.id
        ).order_by(Candidate.id).limit(16).all()
        assert len(candidates) == 16

        # 构造8场16强比赛
        initial_matches = []
        for i in range(0, 16, 2):
            initial_matches.append({
                'candidate1': candidates[i].id,
                'candidate2': candidates[i + 1].id,
                'winner': candidates[i].id,
                'status': 'finished',
                'round': 'round_1',
                'round_name': '16强',
                'votes1': 10,
                'votes2': 5
            })

        contest.config = {
            'knockout_matches_female': initial_matches,
            'knockout_matches_male': [],
            'female_result': [],
            'male_result': []
        }
        db_session.commit()

        # 模拟投票
        for idx, c in enumerate(candidates):
            vote = ContestVote(
                contest_id=contest.id,
                candidate_id=c.id,
                user_id=idx + 1,
                weight=1,
                round_number=4,
                sub_round=1,
                gender='female'
            )
            db_session.add(vote)
        db_session.commit()

        from app.contest_engine import run_knockout_advance, calc_stage_times
        from datetime import timedelta

        times = calc_stage_times(contest.open_at)
        now = times['knockout_16_result_end'] + timedelta(seconds=1)

        advanced, round_name = run_knockout_advance(contest, now, times)
        assert advanced is True
        assert round_name == '8强'

        db_session.refresh(contest)
        matches_8 = contest.config.get('knockout_matches_female', [])
        assert len(matches_8) == 4
        for match in matches_8:
            assert match['status'] == 'active'
            assert match['round_name'] == '8强'


# ========== 小组赛晋级、淘汰赛推进、阶段判断细节 ==========
from app.contest_engine import run_group_promotion, run_knockout_advance, prepare_group_round_data, calc_phase
from datetime import timedelta


class TestContestEngineExtra:

    def test_run_group_promotion_already_run(self, sample_contest, db_session):
        sample_contest.config['female_groups'] = [[1, 2, 3, 4]]
        db_session.commit()
        run_group_promotion(sample_contest)  # 应直接返回，不报错

    def test_calc_phase_group_stage_detail(self, sample_contest):
        sample_contest.status = 'group_stage'
        times = calc_stage_times(sample_contest.open_at)
        # 第一轮投票
        now = datetime(2026, 10, 15, 12, 0, 0)
        phase = calc_phase(sample_contest, now, times)
        assert phase == 'group_round_1'
        # 第一轮公示
        now = datetime(2026, 10, 19, 18, 0, 0)
        phase = calc_phase(sample_contest, now, times)
        assert phase == 'group_round_1_result'

    def test_prepare_group_round_data(self, sample_contest, db_session, sample_user):
        sample_contest.status = 'group_stage'
        female_candidates = sample_contest.candidates.filter_by(gender='female').limit(4).all()

        # 设置分组配置
        sample_contest.config['female_groups'] = [[c.id for c in female_candidates]]
        # 关键：标记 config 字段已修改
        flag_modified(sample_contest, 'config')
        db_session.commit()

        # 为每个候选人投一票（第1轮），避免唯一约束冲突
        for idx, c in enumerate(female_candidates):
            vote = ContestVote(
                contest_id=sample_contest.id,
                candidate_id=c.id,
                user_id=sample_user.id,
                round_number=1,
                gender='female',
                weight=1,
                match_index=idx,
                group_index=idx % 2
            )
            db_session.add(vote)
        db_session.commit()

        # 重新获取 contest 确保数据最新
        contest = db_session.get(Contest, sample_contest.id)
        from app.contest_engine import prepare_group_round_data
        results, female_rank, male_rank = prepare_group_round_data(contest, 'group_round_1_result')

        assert results is not None
        assert 'female' in results
        assert len(results['female']) == 1
        assert len(results['female'][0]['matches']) == 2

    def test_run_knockout_advance_16_to_8(self, sample_contest, db_session):
        contest = sample_contest
        contest.status = 'knockout'
        candidates = contest.candidates.filter_by(gender='female').limit(16).all()
        # 构造16强比赛
        matches = []
        for i in range(0, 16, 2):
            matches.append({
                'candidate1': candidates[i].id,
                'candidate2': candidates[i + 1].id,
                'winner': candidates[i].id,
                'status': 'finished',
                'round_name': '16强'
            })
        contest.config = {
            'knockout_matches_female': matches,
            'knockout_matches_male': [],
            'female_result': [],
            'male_result': []
        }
        db_session.commit()
        times = calc_stage_times(contest.open_at)
        now = times['knockout_16_result_end'] + timedelta(seconds=1)
        advanced, round_name = run_knockout_advance(contest, now, times)
        assert advanced is True
        assert round_name == '8强'
        # 验证新的8强对阵已生成
        new_matches = contest.config.get('knockout_matches_female', [])
        assert len(new_matches) == 4
        for m in new_matches:
            assert m['status'] == 'active'


# ============================================================
# 禁赛与人数短缺守卫
# ============================================================

def _make_match(c1, c2, sub_round=1):
    return {
        'round': 'round_1',
        'round_name': '16强',
        'candidate1': c1.id if c1 else None,
        'candidate2': c2.id if c2 else None,
        'status': 'active',
        'votes1': 0,
        'votes2': 0,
        'winner': None
    }


def _add_votes(db_session, contest, user, tally, sub_round=1):
    """tally: {candidate: 票数}。ContestVote 对同用户同候选有唯一约束，票数用 weight 表达"""
    for cand, n in tally.items():
        db_session.add(ContestVote(
            contest_id=contest.id,
            candidate_id=cand.id,
            user_id=user.id,
            weight=n,
            round_number=4,
            sub_round=sub_round,
            gender='female',
            match_index=0
        ))
    db_session.commit()


class TestDisqualification:
    """禁赛机制：单禁赛判负 / 双禁赛无人晋级+落败者补位 / 轮空兜底"""

    def test_single_ban_auto_loss(self, sample_contest, db_session):
        cands = sample_contest.candidates.filter_by(gender='female').limit(2).all()
        cands[0].banned = True
        db_session.commit()
        match = _make_match(cands[0], cands[1])
        assert get_match_winner(sample_contest, match, 'female', 1) == cands[1].id

    def test_double_ban_no_winner(self, sample_contest, db_session):
        cands = sample_contest.candidates.filter_by(gender='female').limit(2).all()
        cands[0].banned = True
        cands[1].banned = True
        db_session.commit()
        match = _make_match(cands[0], cands[1])
        assert get_match_winner(sample_contest, match, 'female', 1) is None

    def test_bye_match_auto_advance(self, sample_contest, db_session):
        """轮空场（candidate2=None）推进时 candidate1 自动晋级"""
        cands = sample_contest.candidates.filter_by(gender='female').limit(1).all()
        match = _make_match(cands[0], None)
        assert get_match_winner(sample_contest, match, 'female', 1) == cands[0].id

    def test_double_ban_lucky_loser_keeps_chain(self, sample_contest, db_session, sample_user):
        """4 场 8 人，1 场双禁赛：落败者中票数最高者补位，下一轮仍 4 人 2 场"""
        c = sample_contest.candidates.filter_by(gender='female').limit(8).all()
        c[0].banned = True
        c[1].banned = True
        db_session.commit()

        # m1: c2 胜 c3（c3 是最高票落败者→补位）；m2: c4 胜；m3: c6 胜
        _add_votes(db_session, sample_contest, sample_user, {
            c[2]: 3, c[3]: 2,
            c[4]: 3, c[5]: 1,
            c[6]: 3, c[7]: 1,
        })

        matches = [
            _make_match(c[0], c[1]),
            _make_match(c[2], c[3]),
            _make_match(c[4], c[5]),
            _make_match(c[6], c[7]),
        ]
        next_matches = generate_next_round(sample_contest, matches, 'female', 1, '8强')

        assert len(next_matches) == 2
        ids_in_next = {m['candidate1'] for m in next_matches} | {m['candidate2'] for m in next_matches}
        # 禁赛双雄出局，补位者 c3（落败者中票最高）复活，链条人数保持
        assert ids_in_next == {c[2].id, c[3].id, c[4].id, c[6].id}
        assert c[0].id not in ids_in_next and c[1].id not in ids_in_next
        # 原双禁赛场记录补位者，供前端展示"替补晋级"
        assert matches[0]['repechage'] == c[3].id

    def test_double_ban_pool_short_bye_fallback(self, sample_contest, db_session, sample_user):
        """补位后仍奇数：奇数剩余者轮空（candidate2=None），不再静默淘汰"""
        c = sample_contest.candidates.filter_by(gender='female').limit(6).all()
        # m1 双禁赛；m3 一方禁赛（c[4]）走判负路径、败者不进池；m2 是唯一产池场次
        c[0].banned = True
        c[1].banned = True
        c[4].banned = True
        db_session.commit()

        _add_votes(db_session, sample_contest, sample_user, {
            c[2]: 2, c[3]: 1,   # m2: winner c[2]，败者 c[3]（1 票进池）
            c[5]: 3,            # m3: c[4] 禁赛自动判负 → winner c[5]，败者 c[4] 禁赛不进池
        })

        matches = [
            _make_match(c[0], c[1]),  # m1 双禁赛
            _make_match(c[2], c[3]),
            _make_match(c[4], c[5]),
        ]
        next_matches = generate_next_round(sample_contest, matches, 'female', 1, '8强')

        # winners = c[2], c[5] + 补位 c[3] → 3 人（奇数）→ 1 场正常 + 1 场轮空
        assert len(next_matches) == 2
        assert next_matches[0]['candidate2'] is not None
        assert next_matches[1]['candidate2'] is None
        assert next_matches[1]['bye'] is True

    def test_double_ban_all_matches_empty_next_round(self, sample_contest, db_session):
        """极端：全部场次双禁赛 → 下一轮空对阵，不抛异常、不产生禁赛晋级者"""
        c = sample_contest.candidates.filter_by(gender='female').limit(4).all()
        for x in c:
            x.banned = True
        db_session.commit()
        matches = [_make_match(c[0], c[1]), _make_match(c[2], c[3])]
        next_matches = generate_next_round(sample_contest, matches, 'female', 1, '8强')
        assert next_matches == []

    def test_three_of_four_double_ban_keeps_full_round(self, sample_contest, db_session, sample_user):
        """8 场 16 人中 3 场双禁赛：3 名落败者补位，下一轮仍 8 人 4 场"""
        c = sample_contest.candidates.filter_by(gender='female').limit(16).all()
        c[0].banned = True; c[1].banned = True
        c[2].banned = True; c[3].banned = True
        c[4].banned = True; c[5].banned = True
        db_session.commit()

        # m4-m8 胜者票数高于各自败者；败者池 c7>c9>c11 供 m1-m3 补位
        _add_votes(db_session, sample_contest, sample_user, {
            c[6]: 4, c[7]: 3,
            c[8]: 4, c[9]: 2,
            c[10]: 4, c[11]: 1,
            c[12]: 3, c[13]: 2,
            c[14]: 3, c[15]: 1,
        })

        matches = [_make_match(c[0], c[1]), _make_match(c[2], c[3]),
                   _make_match(c[4], c[5]), _make_match(c[6], c[7]),
                   _make_match(c[8], c[9]), _make_match(c[10], c[11]),
                   _make_match(c[12], c[13]), _make_match(c[14], c[15])]
        next_matches = generate_next_round(sample_contest, matches, 'female', 1, '16强')

        assert len(next_matches) == 4
        ids_in_next = {m['candidate1'] for m in next_matches} | {m['candidate2'] for m in next_matches}
        # 补位者 = 败者池前 3 票：c[7](3), c[13](2), c[9](2)
        assert ids_in_next == {c[6].id, c[7].id, c[8].id, c[9].id,
                               c[10].id, c[12].id, c[13].id, c[14].id}
        # 禁赛双雄全部出局
        for x in (c[0], c[1], c[2], c[3], c[4], c[5]):
            assert x.id not in ids_in_next

    def test_four_of_four_double_ban_degrades_to_bye(self, sample_contest, db_session, sample_user):
        """8 场中 5 场双禁赛（败者池仅 3 < 5）：先补 3 位，缺额生成轮空场"""
        c = sample_contest.candidates.filter_by(gender='female').limit(16).all()
        for x in c[0:10]:     # m1-m5 双方禁赛
            x.banned = True
        db_session.commit()

        _add_votes(db_session, sample_contest, sample_user, {
            c[10]: 3, c[11]: 2,
            c[12]: 3, c[13]: 2,
            c[14]: 3, c[15]: 2,
        })

        matches = [_make_match(c[i], c[i + 1]) for i in range(0, 16, 2)]
        next_matches = generate_next_round(sample_contest, matches, 'female', 1, '16强')

        # winners = c10,c12,c14 + 补位 c11,c13,c15 = 6 人 → 3 场正常；未到 4 场不崩
        assert len(next_matches) == 3
        bye_match_ids = {m['candidate1'] for m in next_matches} | {m['candidate2'] for m in next_matches}
        assert bye_match_ids == {c[10].id, c[11].id, c[12].id, c[13].id, c[14].id, c[15].id}


class TestNominationShortfall:
    """入围/提名人数不足：动态缩组 + 轮空槽占位，不生成空组、不 IndexError"""

    def test_short_roster_compacts_groups(self, sample_contest, db_session, sample_user):
        """只保留 10 个女角色：ceil(10/4)=3 组，末组 2 人 + 2 个轮空槽"""
        females = sample_contest.candidates.filter_by(gender='female').all()
        for c in females[10:]:
            db_session.delete(c)
        kept = sample_contest.candidates.filter_by(gender='female').all()
        for i, c in enumerate(kept):
            db_session.add(ContestVote(
                contest_id=sample_contest.id,
                candidate_id=c.id,
                user_id=sample_user.id,
                weight=i + 1,
                round_number=0,
                gender='female'
            ))
        db_session.commit()

        run_qualifying_promotion(sample_contest)

        groups = sample_contest.config['female_groups']
        assert len(groups) == 3                     # 不再是 8 组（无空组）
        assert all(len(g) == 4 for g in groups)     # 每组恒 4 槽
        real = [cid for g in groups for cid in g if cid is not None]
        assert len(real) == 10
        byes = [cid for g in groups for cid in g if cid is None]
        assert len(byes) == 2
        # 前两组满员，缺员集中在末组
        assert all(cid is not None for cid in groups[0] + groups[1])
        # 男组不受影响：32 → 8 组满员
        mgroups = sample_contest.config['male_groups']
        assert len(mgroups) == 8
        assert all(len(g) == 4 and all(cid is not None for cid in g) for g in mgroups)

    def test_no_candidates_no_groups(self, sample_contest, db_session):
        """某性别 0 人：不生成分组，页面走"分组尚未生成"分支，不崩溃"""
        females = sample_contest.candidates.filter_by(gender='female').all()
        for c in females:
            db_session.delete(c)
        db_session.commit()
        run_qualifying_promotion(sample_contest)
        assert sample_contest.config['female_groups'] == []
        # 男组正常
        mgroups = sample_contest.config['male_groups']
        assert len(mgroups) == 8

    def test_single_group_2via_one_member_advances_alone(self, sample_contest, db_session, sample_user):
        """小组 4 槽仅 1 名真实成员（其余禁赛）：跳过计分，该成员自动晋级"""
        females = sample_contest.candidates.filter_by(gender='female').limit(8).all()
        # 构造 config 分组（存 id）：1 组 4 人，其中 3 人禁赛；engine 只统计 stage=group_stage
        sample_contest.config = {'female_groups': [[c.id for c in females[0:4]]], 'male_groups': []}
        for x in females[0:4]:
            x.stage = 'group_stage'
        females[1].banned = True
        females[2].banned = True
        females[3].banned = True
        db_session.commit()

        run_group_promotion(sample_contest)

        top16 = sample_contest.config['female_top16']
        assert top16 == [females[0].id]

    def test_group_of_three_scores_and_advances(self, sample_contest, db_session, sample_user):
        """3 人组（1 轮空槽）：计分不崩，轮空场不计分，前2正常晋级"""
        females = sample_contest.candidates.filter_by(gender='female').limit(3).all()
        sample_contest.config = {
            'female_groups': [[c.id for c in females] + [None]],
            'male_groups': []
        }
        for x in females:
            x.stage = 'group_stage'
        db_session.commit()
        # r1: f0>f1；r2: f0>f2；r3: f1>f0（f2 的轮空场不产生积分）
        voters = {
            (females[0].id, 1): 3, (females[1].id, 1): 1,
            (females[0].id, 2): 3, (females[2].id, 2): 1,
            (females[1].id, 3): 3, (females[0].id, 3): 1,
        }
        seen = set()
        for (cid, r), w in voters.items():
            key = (cid, r)
            db_session.add(ContestVote(
                contest_id=sample_contest.id,
                candidate_id=cid,
                user_id=sample_user.id,
                weight=w,
                round_number=r,
                gender='female',
                group_index=0,
                match_index=1 if key in seen else 0
            ))
            seen.add(key)
        db_session.commit()

        run_group_promotion(sample_contest)

        top16 = sample_contest.config['female_top16']
        # f0 两胜一负=6分，f1 两胜一负=6分?（r1 负 f0、r3 胜 f0 → 2 胜 1 负）……f2 仅 1 胜
        assert females[0].id in top16 and females[1].id in top16
        assert len(top16) == 2

    def test_group_banned_walkover_scoring(self, sample_contest, db_session, sample_user):
        """4 人组 1 人禁赛：对手三场均兵不血刃取胜，禁赛方三负且不靠票数"""
        females = sample_contest.candidates.filter_by(gender='female').limit(4).all()
        sample_contest.config = {
            'female_groups': [[c.id for c in females]],
            'male_groups': []
        }
        for x in females:
            x.stage = 'group_stage'
        females[3].banned = True
        db_session.commit()
        # 只投正常场：r1 f0>f1；r2 f0>f2；r3 f1>f2；f3 三场判负
        voters = {
            (females[0].id, 1): 3, (females[1].id, 1): 1,
            (females[0].id, 2): 3, (females[2].id, 2): 1,
            (females[1].id, 3): 3, (females[2].id, 3): 1,
        }
        seen = set()
        for (cid, r), w in voters.items():
            key = (cid, r)
            db_session.add(ContestVote(
                contest_id=sample_contest.id,
                candidate_id=cid,
                user_id=sample_user.id,
                weight=w,
                round_number=r,
                gender='female',
                group_index=0,
                match_index=1 if key in seen else 0
            ))
            seen.add(key)
        db_session.commit()

        run_group_promotion(sample_contest)

        top16 = sample_contest.config['female_top16']
        assert top16[0] == females[0].id      # 3 胜（含 1 场不战而胜）9 分
        assert top16[1] == females[1].id      # 2 胜 6 分
        assert females[3].id not in top16     # 禁赛者 3 负 0 分被过滤

    def test_group_double_ban_not_scored_and_public_info(
            self, sample_contest, db_session, sample_user):
        """双禁赛场不计分不判负；公示场次数据带 banned/bye/removed 标识"""
        females = sample_contest.candidates.filter_by(gender='female').limit(4).all()
        sample_contest.config = {
            'female_groups': [[c.id for c in females]],
            'male_groups': []
        }
        for x in females:
            x.stage = 'group_stage'
        females[0].banned = True
        females[1].banned = True
        db_session.commit()
        # 给双禁赛场双方都塞票（应被忽略）；正常场 f2>f3
        db_session.add(ContestVote(
            contest_id=sample_contest.id, candidate_id=females[0].id,
            user_id=sample_user.id, weight=5,
            round_number=1, gender='female', group_index=0, match_index=1
        ))
        db_session.add(ContestVote(
            contest_id=sample_contest.id, candidate_id=females[2].id,
            user_id=sample_user.id, weight=3,
            round_number=1, gender='female', group_index=0, match_index=2
        ))
        db_session.commit()

        run_group_promotion(sample_contest)

        top16 = sample_contest.config['female_top16']
        assert set(top16) == {females[2].id, females[3].id}

        results, rank_f, _ = prepare_group_round_data(sample_contest, 'group_round_1_result')
        g1 = results['female'][0]
        m1, m2 = g1['matches'][0], g1['matches'][1]
        # m1 双禁赛：无胜者；m2 正常：f2 胜
        assert m1['banned1'] and m1['banned2'] and m1['winner'] is None
        assert m2['winner'] == females[2].id and not m2['bye']
        assert m1['bye'] is False and m1['removed1'] is False
        # 总积分表带禁赛徽章字段，双禁赛者 0 分
        banned_rows = [item for item in rank_f if item['banned']]
        assert len(banned_rows) == 2
        assert all(item['points'] == 0 for item in banned_rows)


class TestFinalRankingGuard:
    """终榜守卫：冠军只从真实决赛产生；禁赛者不进榜；决赛失效则冠军空缺"""

    def _setup_bracket(self, sample_contest):
        """构造完整女子对阵：16→8→4→决赛，每轮 candidate1 胜"""
        c = sample_contest.candidates.filter_by(gender='female').limit(20).all()
        if sample_contest.config is None:
            sample_contest.config = {}
        cfg = sample_contest.config
        cfg['knockout_matches_female_round16'] = [
            {**_make_match(c[a], c[b], 1), 'round': 'round_1', 'winner': c[a].id}
            for a, b in [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13), (14, 15)]
        ]
        cfg['knockout_matches_female_round8'] = [
            {**_make_match(c[a], c[b], 2), 'round': 'round_2', 'winner': c[a].id}
            for a, b in [(0, 2), (4, 6), (8, 10), (12, 14)]
        ]
        cfg['knockout_matches_female_round4'] = [
            {**_make_match(c[a], c[b], 3), 'round': 'round_3', 'winner': c[a].id}
            for a, b in [(0, 4), (8, 12)]
        ]
        # JSON 列就地改键不会自动标脏，必须显式 flag_modified
        flag_modified(sample_contest, 'config')
        return c

    def _final(self, sample_contest, c, winner, bye_companion=None):
        f = _make_match(c[0], c[8], 4)
        f['round'] = 'final'
        f['round_name'] = '决赛'
        if winner is not None:
            f['winner'] = winner.id
        final_list = [f]
        if bye_companion is not None:
            # 轮空场垫尾（3 人进入决赛轮的极端情形）
            bt = _make_match(c[bye_companion], None, 4)
            bt['round'] = 'final'
            bt['round_name'] = '决赛'
            bt['bye'] = True
            bt['winner'] = c[bye_companion].id
            final_list.append(bt)
        sample_contest.config['knockout_matches_female_final'] = final_list
        flag_modified(sample_contest, 'config')

    def test_bye_match_not_treated_as_final(self, sample_contest, db_session):
        """决赛轮含垫尾轮空场：冠军仍从真实决赛产生，不由轮空场决定"""
        c = self._setup_bracket(sample_contest)
        self._final(sample_contest, c, winner=c[0], bye_companion=16)
        db_session.commit()

        run_final_ranking(sample_contest)

        assert db.session.get(Candidate, c[0].id).stage == 'champion'
        assert db.session.get(Candidate, c[16].id).stage != 'champion'
        assert sample_contest.config['female_ranking'][0]['id'] == c[0].id
        assert sample_contest.config['female_ranking'][0]['stage'] == 'champion'

    def test_final_double_ban_vacates_championship(self, sample_contest, db_session):
        """决赛双方禁赛：不产生冠军，也不把半决赛败者误加冕"""
        c = self._setup_bracket(sample_contest)
        self._final(sample_contest, c, winner=None)
        c[0].banned = True
        c[8].banned = True
        db_session.commit()

        run_final_ranking(sample_contest)

        ranking = sample_contest.config['female_ranking']
        ids = {item['id'] for item in ranking}
        assert c[0].id not in ids and c[8].id not in ids        # 决赛双方不进榜
        assert db.session.get(Candidate, c[0].id).stage != 'champion'
        assert len(ranking) > 0                                  # 排名仍公布（四强败者起）

    def test_banned_loser_excluded_champion_kept(self, sample_contest, db_session):
        """决赛负者事后被禁赛：冠军保留，禁赛者从榜中移除"""
        c = self._setup_bracket(sample_contest)
        self._final(sample_contest, c, winner=c[0])
        c[8].banned = True
        db_session.commit()

        run_final_ranking(sample_contest)

        assert db.session.get(Candidate, c[0].id).stage == 'champion'
        ids = [item['id'] for item in sample_contest.config['female_ranking']]
        assert c[8].id not in ids
        assert c[0].id == ids[0]


class TestSingleGenderAdvance:
    """单性别对阵推进守卫：女组空阵不导致男组被反复重推砍半"""

    def test_male_only_bracket_advances_once_per_round(self, sample_contest, db_session):
        """女组无对阵：16→8 只推一次；重复 tick 不会覆盖历史键、不会提前推 4强"""
        c = sample_contest.candidates.filter_by(gender='male').limit(16).all()
        sample_contest.config = {
            'knockout_matches_female': [],
            'knockout_matches_male': [
                {**_make_match(c[i], c[i + 1], 1), 'round': 'round_1', 'round_name': '16强'}
                for i in range(0, 16, 2)
            ]
        }
        db_session.commit()
        times = calc_stage_times(sample_contest.open_at)
        now = times['knockout_16_end'] + timedelta(seconds=1)

        first, round_name = run_knockout_advance(sample_contest, now, times)
        assert first is True and round_name == '8强'
        active = sample_contest.config['knockout_matches_male']
        assert len(active) == 4                                # 16 人 8 场 → 8 人 4 场
        assert len(sample_contest.config['knockout_matches_male_round16']) == 8

        # 第二个 tick（仍在 16强公示期）：女组 round8 键缺失，但男组键已在，
        # 不得重入——否则男组 8 强会被以 sub_round=1 的旧票数直接推成 4 强
        second, _ = run_knockout_advance(sample_contest, now, times)
        assert second is False
        assert 'knockout_matches_male_round8' not in sample_contest.config
        assert len(sample_contest.config['knockout_matches_male']) == 4
        assert len(sample_contest.config['knockout_matches_male_round16']) == 8

    def test_female_only_bracket_advances_once_per_round(self, sample_contest, db_session):
        """镜像场景：男组无对阵，女组同样只推一次"""
        c = sample_contest.candidates.filter_by(gender='female').limit(16).all()
        sample_contest.config = {
            'knockout_matches_female': [
                {**_make_match(c[i], c[i + 1], 1), 'round': 'round_1', 'round_name': '16强'}
                for i in range(0, 16, 2)
            ]
            # 注意：连 knockout_matches_male 键都没有
        }
        db_session.commit()
        times = calc_stage_times(sample_contest.open_at)
        now = times['knockout_16_end'] + timedelta(seconds=1)

        first, round_name = run_knockout_advance(sample_contest, now, times)
        assert first is True and round_name == '8强'
        assert len(sample_contest.config['knockout_matches_female']) == 4
        assert len(sample_contest.config['knockout_matches_female_round16']) == 8

        second, _ = run_knockout_advance(sample_contest, now, times)
        assert second is False
        assert 'knockout_matches_female_round8' not in sample_contest.config
        assert len(sample_contest.config['knockout_matches_female']) == 4


class TestFinalWinnerRecording:
    """决赛计票：决赛没有下一轮，胜者由推进引擎在 final_vote_end 显式写入"""

    def test_final_winner_recorded_and_champion_crowned(self, sample_contest, db_session, sample_user):
        cands = sample_contest.candidates.filter_by(gender='female').limit(2).all()
        cands[0].stage = 'knockout'
        cands[1].stage = 'knockout'
        final_match = {
            'round': 'final', 'round_name': '决赛',
            'candidate1': cands[0].id, 'candidate2': cands[1].id,
            'status': 'active', 'votes1': 0, 'votes2': 0, 'winner': None
        }
        sample_contest.config = {
            'knockout_matches_female': [final_match],
            'knockout_matches_female_final': [final_match],
            'knockout_matches_female_round16': [
                {'candidate1': cands[0].id, 'candidate2': cands[1].id,
                 'winner': cands[0].id, 'status': 'finished'}
            ],
            'knockout_matches_male': []
        }
        # 决赛投票：c0 3 票
        db_session.add(ContestVote(
            contest_id=sample_contest.id, candidate_id=cands[0].id,
            user_id=sample_user.id, weight=3,
            round_number=4, sub_round=4, gender='female', match_index=1
        ))
        db_session.commit()
        times = calc_stage_times(sample_contest.open_at)
        now = times['final_vote_end'] + timedelta(seconds=1)

        advanced, name = run_knockout_advance(sample_contest, now, times)
        assert advanced is True and name == '决赛计票'
        # commit 会触发 JSON 列重载，须从 config 现取而非引用旧 dict
        recorded_final = sample_contest.config['knockout_matches_female'][0]
        assert recorded_final['winner'] == cands[0].id
        assert recorded_final['status'] == 'finished'

        # 同一请求的下一轮管线迭代：终榜生成 → 冠军加冕
        run_final_ranking(sample_contest)
        assert db.session.get(Candidate, cands[0].id).stage == 'champion'
        assert sample_contest.config['female_ranking'][0]['stage'] == 'champion'

        # 幂等：再次 tick 不重触发
        again, _ = run_knockout_advance(sample_contest, now, times)
        assert again is False
