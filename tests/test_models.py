import pytest
from app.models import User, Contest, Nomination, Candidate, ContestVote, Activity, AnimeResource, Message, Reply
from datetime import datetime, timedelta


class TestUserModel:
    """用户模型测试"""

    def test_create_user(self, db_session):
        user = User(username="testuser", qq="123456789")
        user.set_password("testpass")
        db_session.add(user)
        db_session.commit()
        saved = User.query.first()
        assert saved.username == "testuser"
        assert saved.check_password("testpass") is True
        assert saved.is_staff is False
        assert saved.is_owner is False

    def test_unique_username(self, db_session):
        user1 = User(username="unique", qq="111111111")
        user1.set_password("pass")
        db_session.add(user1)
        db_session.commit()
        user2 = User(username="unique", qq="222222222")
        user2.set_password("pass")
        db_session.add(user2)
        with pytest.raises(Exception):
            db_session.commit()


class TestContestModel:
    """赛事模型测试"""

    def test_create_contest(self, db_session):
        open_at = datetime(2026, 10, 1, 18, 0, 0)
        contest = Contest(
            title="测试萌战",
            description="测试描述",
            status='draft',
            open_at=open_at,
            close_at=open_at + timedelta(days=50)
        )
        db_session.add(contest)
        db_session.commit()
        saved = Contest.query.first()
        assert saved.title == "测试萌战"
        assert saved.status == "draft"

    def test_contest_config_json(self, db_session):
        contest = Contest(title="配置测试", description="desc")
        contest.config = {'key': 'value'}
        db_session.add(contest)
        db_session.commit()
        saved = Contest.query.first()
        assert saved.config['key'] == 'value'


class TestNominationModel:
    """提名模型测试"""

    def test_create_nomination(self, db_session, sample_user, sample_contest):
        nom = Nomination(
            contest_id=sample_contest.id,
            user_id=sample_user.id,
            name="角色A",
            source="作品X",
            gender='female',
            status='pending'
        )
        db_session.add(nom)
        db_session.commit()
        saved = Nomination.query.first()
        assert saved.name == "角色A"
        assert saved.status == "pending"


class TestCandidateModel:
    """候选角色模型测试"""

    def test_create_candidate(self, db_session, sample_contest):
        cand = Candidate(
            contest_id=sample_contest.id,
            name="候选角色",
            source="测试作品",
            gender='female',
            stage='pending'
        )
        db_session.add(cand)
        db_session.commit()
        saved = db_session.get(Candidate, cand.id)  # 使用 id 精确获取
        assert saved.name == "候选角色"

    def test_candidate_stage_transition(self, db_session, sample_contest):
        cand = Candidate(
            contest_id=sample_contest.id,
            name="晋级测试",
            source="作品",
            gender='male',
            stage='pending'
        )
        db_session.add(cand)
        db_session.commit()
        cand.stage = 'group_stage'
        db_session.commit()
        saved = db_session.get(Candidate, cand.id)  # 使用 id 精确获取
        assert saved.stage == 'group_stage'


class TestContestVoteModel:
    """投票模型测试"""

    def test_create_vote(self, db_session, sample_contest, sample_user, sample_candidate):
        vote = ContestVote(
            contest_id=sample_contest.id,
            candidate_id=sample_candidate.id,
            user_id=sample_user.id,
            weight=3,
            round_number=0,
            gender='female'
        )
        db_session.add(vote)
        db_session.commit()
        saved = ContestVote.query.first()
        assert saved.weight == 3
        assert saved.round_number == 0

    def test_vote_default_values(self, db_session, sample_contest, sample_user, sample_candidate):
        vote = ContestVote(
            contest_id=sample_contest.id,
            candidate_id=sample_candidate.id,
            user_id=sample_user.id
        )
        db_session.add(vote)
        db_session.commit()
        saved = ContestVote.query.first()
        assert saved.weight == 1
        assert saved.round_number == 0
        assert saved.sub_round == 0
        assert saved.match_index == 0


class TestActivityModel:
    """活动模型测试"""

    def test_create_activity(self, db_session):
        activity = Activity(title="测试活动", date="2026-10-15", content="内容")
        db_session.add(activity)
        db_session.commit()
        saved = Activity.query.first()
        assert saved.title == "测试活动"


class TestAnimeResourceModel:
    """番剧资源模型测试"""

    def test_create_anime(self, db_session, sample_user):
        anime = AnimeResource(
            title="测试番剧",
            link="https://test.com",
            user_id=sample_user.id,
            status='pending'
        )
        db_session.add(anime)
        db_session.commit()
        saved = AnimeResource.query.first()
        assert saved.title == "测试番剧"
        assert saved.status == "pending"


class TestMessageModel:
    """留言模型测试"""

    def test_create_message(self, db_session, sample_user):
        msg = Message(
            nickname=sample_user.username,
            content="测试留言",
            user_id=sample_user.id
        )
        db_session.add(msg)
        db_session.commit()
        saved = Message.query.first()
        assert saved.content == "测试留言"


class TestReplyModel:
    """回复模型测试"""

    def test_create_reply(self, db_session, sample_user, sample_message):
        reply = Reply(
            nickname=sample_user.username,
            content="测试回复",
            message_id=sample_message.id,
            user_id=sample_user.id
        )
        db_session.add(reply)
        db_session.commit()
        saved = Reply.query.first()
        assert saved.content == "测试回复"
        assert saved.message_id == sample_message.id

    def test_nested_reply(self, db_session, sample_user, sample_message):
        # 创建一级回复
        reply1 = Reply(
            nickname=sample_user.username,
            content="一级回复",
            message_id=sample_message.id,
            user_id=sample_user.id
        )
        db_session.add(reply1)
        db_session.commit()
        # 创建二级回复（回复 reply1）
        reply2 = Reply(
            nickname=sample_user.username,
            content="二级回复",
            message_id=sample_message.id,
            user_id=sample_user.id,
            parent_reply_id=reply1.id
        )
        db_session.add(reply2)
        db_session.commit()
        saved = Reply.query.filter_by(parent_reply_id=reply1.id).first()
        assert saved is not None
        assert saved.content == "二级回复"
