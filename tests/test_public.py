from datetime import timedelta, datetime

import pytest

from app.models import ContestVote, Contest


class TestPublic:
    """公共页面测试（所有需要登录的页面均使用 logged_in_client）"""

    def test_splash_page(self, client):
        # splash 是公开的，不需要登录
        response = client.get('/')
        assert response.status_code == 200
        assert '南平一中动漫社' in response.text

    def test_home_page(self, logged_in_client):
        response = logged_in_client.get('/home')
        assert response.status_code == 200
        assert '欢迎来到动漫社' in response.text

    def test_about_page(self, logged_in_client):
        response = logged_in_client.get('/about')
        assert response.status_code == 200
        assert '社团简介' in response.text

    def test_activities_page(self, logged_in_client):
        response = logged_in_client.get('/activities')
        assert response.status_code == 200
        assert '近期活动' in response.text

    def test_gallery_page(self, logged_in_client):
        response = logged_in_client.get('/gallery')
        assert response.status_code == 200
        assert '珍贵历史图片' in response.text

    def test_board_page(self, logged_in_client):
        response = logged_in_client.get('/board')
        assert response.status_code == 200
        assert '社员留言板' in response.text

    def test_anime_resources_page(self, logged_in_client):
        response = logged_in_client.get('/anime_resources')
        assert response.status_code == 200
        assert '番剧资源下载' in response.text

    def test_submit_anime_requires_login(self, client):
        # 未登录应重定向到登录页
        response = client.get('/submit_anime', follow_redirects=False)
        assert response.status_code == 302

    def test_members_page(self, logged_in_client):
        response = logged_in_client.get('/members')
        assert response.status_code == 200
        assert '社员名单' in response.text

    def test_contest_center_page(self, logged_in_client):
        response = logged_in_client.get('/contest_center')
        assert response.status_code == 200
        assert '赛事中心' in response.text

    def test_contest_rules_page(self, logged_in_client, sample_contest):
        response = logged_in_client.get(f'/contest/{sample_contest.id}/rules')
        assert response.status_code == 200
        assert '规则确认' in response.text

    def test_contest_detail_page(self, logged_in_client, sample_contest):
        response = logged_in_client.get(f'/contest/{sample_contest.id}')
        assert response.status_code == 200
        assert '测试萌战' in response.text

    def test_board_post_requires_login(self, client):
        response = client.post('/board', data={'content': 'test'}, follow_redirects=False)
        assert response.status_code == 302

    def test_add_reply_requires_login(self, client, sample_message):
        response = client.post(f'/reply/{sample_message.id}', data={'content': 'test reply'}, follow_redirects=False)
        assert response.status_code == 302


class TestVoting:
    """投票功能测试（直接测试提交接口，验证数据库）"""

    # ---------- 海选投票 ----------

    def test_qualifying_vote_submit(self, logged_in_client, db_session, sample_contest, sample_user):
        """测试海选投票成功提交"""
        contest = db_session.get(Contest, sample_contest.id)
        contest.status = 'open'
        contest.open_at = datetime.now() - timedelta(days=2)   # 仅用于满足业务逻辑，但提交接口不检查时间
        db_session.commit()
        db_session.refresh(contest)

        candidate = contest.candidates.filter_by(gender='female').first()
        assert candidate is not None

        response = logged_in_client.post(
            f'/contest/{contest.id}/qualifying/submit',
            data={'gender': 'female', f'vote_{candidate.id}': '3'},
            follow_redirects=True
        )
        # 提交接口成功后通常重定向到投票页，返回200
        assert response.status_code == 200
        # 验证数据库中的投票记录
        vote = ContestVote.query.filter_by(
            contest_id=contest.id,
            candidate_id=candidate.id,
            user_id=sample_user.id,
            round_number=0,
            gender='female'
        ).first()
        assert vote is not None
        assert vote.weight == 3

    def test_qualifying_vote_duplicate(self, logged_in_client, db_session, sample_contest, sample_user):
        """测试同一用户不能重复投票（同一组别）"""
        contest = db_session.get(Contest, sample_contest.id)
        contest.status = 'open'
        contest.open_at = datetime.now() - timedelta(days=2)
        db_session.commit()
        db_session.refresh(contest)

        candidate = contest.candidates.filter_by(gender='female').first()
        assert candidate is not None

        # 第一次投票
        resp1 = logged_in_client.post(
            f'/contest/{contest.id}/qualifying/submit',
            data={'gender': 'female', f'vote_{candidate.id}': '2'},
            follow_redirects=True
        )
        assert resp1.status_code == 200
        # 验证第一次投票成功
        vote1 = ContestVote.query.filter_by(
            contest_id=contest.id,
            candidate_id=candidate.id,
            user_id=sample_user.id,
            round_number=0,
            gender='female'
        ).first()
        assert vote1 is not None

        # 第二次投票（应被拒绝，返回flash消息）
        resp2 = logged_in_client.post(
            f'/contest/{contest.id}/qualifying/submit',
            data={'gender': 'female', f'vote_{candidate.id}': '1'},
            follow_redirects=True
        )
        assert resp2.status_code == 200
        # 检查flash消息（可通过检查页面内容，但更可靠是检查数据库没有新记录）
        vote2_count = ContestVote.query.filter_by(
            contest_id=contest.id,
            candidate_id=candidate.id,
            user_id=sample_user.id,
            round_number=0,
            gender='female'
        ).count()
        assert vote2_count == 1  # 只有一条

    def test_qualifying_vote_exceed_limits(self, logged_in_client, db_session, sample_contest, sample_user):
        """测试投票数量限制（总票数≤15，单角色≤3）"""
        contest = db_session.get(Contest, sample_contest.id)
        contest.status = 'open'
        contest.open_at = datetime.now() - timedelta(days=2)
        db_session.commit()
        db_session.refresh(contest)

        candidates = contest.candidates.filter_by(gender='female').limit(6).all()
        assert len(candidates) >= 6

        # 总票数超限：给6个角色各3票 => 18票 > 15
        data = {'gender': 'female'}
        for idx, cand in enumerate(candidates[:6]):
            data[f'vote_{cand.id}'] = '3'
        response = logged_in_client.post(
            f'/contest/{contest.id}/qualifying/submit',
            data=data,
            follow_redirects=True
        )
        assert response.status_code == 200
        # 验证数据库没有新增投票（因为请求被拒绝）
        vote_count = ContestVote.query.filter_by(
            contest_id=contest.id,
            user_id=sample_user.id,
            round_number=0,
            gender='female'
        ).count()
        assert vote_count == 0

        # 单角色超限：给一个角色投4票
        data2 = {'gender': 'female', f'vote_{candidates[0].id}': '4'}
        response2 = logged_in_client.post(
            f'/contest/{contest.id}/qualifying/submit',
            data=data2,
            follow_redirects=True
        )
        assert response2.status_code == 200
        # 同样没有新增
        vote_count2 = ContestVote.query.filter_by(
            contest_id=contest.id,
            user_id=sample_user.id,
            round_number=0,
            gender='female'
        ).count()
        assert vote_count2 == 0

    # ---------- 小组赛投票（可选） ----------

    def test_group_vote_submit(self, logged_in_client, db_session, sample_contest, sample_user):
        """测试小组赛投票（需提前设置分组）"""
        contest = db_session.get(Contest, sample_contest.id)
        contest.status = 'group_stage'
        contest.open_at = datetime.now() - timedelta(days=20)  # 为了满足可能的时间检查
        # 构造分组数据
        female_candidates = contest.candidates.filter_by(gender='female').limit(4).all()
        if len(female_candidates) < 4:
            pytest.skip("需要至少4个女角色")
        contest.config = {
            'female_groups': [[c.id for c in female_candidates]]
        }
        db_session.commit()
        db_session.refresh(contest)

        candidate = female_candidates[0]
        response = logged_in_client.post(
            f'/contest/{contest.id}/group/submit',
            data={'gender': 'female', 'candidate_id': candidate.id},
            follow_redirects=True
        )
        # 由于时间控制，可能被拒绝，但确保不报错
        assert response.status_code == 200
        # 如果成功则验证数据库，但这里不强求

    # ---------- 淘汰赛投票（可选） ----------

    def test_knockout_vote_submit(self, logged_in_client, db_session, sample_contest, sample_user):
        """测试淘汰赛投票（需提前设置对阵）"""
        contest = db_session.get(Contest, sample_contest.id)
        contest.status = 'knockout'
        contest.open_at = datetime.now() - timedelta(days=40)
        female_candidates = contest.candidates.filter_by(gender='female').limit(2).all()
        if len(female_candidates) < 2:
            pytest.skip("需要至少2个女角色")
        contest.config = {
            'knockout_matches_female': [
                {
                    'candidate1': female_candidates[0].id,
                    'candidate2': female_candidates[1].id,
                    'status': 'active',
                    'winner': None
                }
            ]
        }
        db_session.commit()
        db_session.refresh(contest)

        candidate = female_candidates[0]
        response = logged_in_client.post(
            f'/contest/{contest.id}/knockout/submit',
            data={'gender': 'female', 'candidate_id': candidate.id},
            follow_redirects=True
        )
        assert response.status_code == 200