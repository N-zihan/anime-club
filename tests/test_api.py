import pytest
from app.models import ContestVote, Candidate

class TestAPI:
    """API 端点测试"""

    def test_api_votes_returns_json(self, logged_in_client, db_session, sample_contest, sample_user, sample_candidate):
        """获取候选人票数"""
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

        response = logged_in_client.get(f'/api/votes/{sample_candidate.id}')
        assert response.status_code == 200
        assert response.json['total_votes'] == 3

    def test_api_votes_zero_if_no_votes(self, logged_in_client, db_session, sample_contest):
        """没有投票返回 0"""
        from app.models import Candidate
        cand = Candidate(
            contest_id=sample_contest.id,
            name="无人投票",
            source="测试",
            gender='male'
        )
        db_session.add(cand)
        db_session.commit()

        response = logged_in_client.get(f'/api/votes/{cand.id}')
        assert response.status_code == 200
        assert response.json['total_votes'] == 0

    def test_api_votes_404_for_invalid_candidate(self, logged_in_client):
        """无效 candidate_id 返回 404"""
        response = logged_in_client.get('/api/votes/99999')
        assert response.status_code == 404
        assert response.json['error'] == 'Candidate not found'