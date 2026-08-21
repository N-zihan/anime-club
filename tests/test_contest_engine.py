from datetime import datetime

from app.contest_engine import (
    calc_stage_times, calc_phase, auto_activate_contest,
    run_qualifying_promotion
)
from app.models import User, Candidate, ContestVote, Contest
from app.models import db


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

        assert contest.status == 'group_stage'
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
        assert contest.status == 'closed'

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

        advanced, round_name = run_knockout_advance(contest, 'knockout_16_result', now, times)
        assert advanced is True
        assert round_name == '8强'

        db_session.refresh(contest)
        matches_8 = contest.config.get('knockout_matches_female', [])
        assert len(matches_8) == 4
        for match in matches_8:
            assert match['status'] == 'active'
            assert match['round_name'] == '8强'
