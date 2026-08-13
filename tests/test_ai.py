import pytest
from unittest.mock import patch, MagicMock
from app.ai import generate_commentary, generate_prediction, _get_cached, _set_cache, _cache
from app.models import Contest, Candidate


class TestAICommentary:
    """测试 AI 实时战报"""

    def test_commentary_not_started(self, db_session, sample_contest):
        """赛事未开始时，直接返回提示，不调用 API"""
        contest = sample_contest
        contest.status = 'draft'
        db_session.commit()

        success, content, error = generate_commentary(contest.id, 'not_started')

        assert success is True
        assert '赛事尚未开始' in content
        assert error is None

    def test_commentary_with_no_candidates(self, db_session, sample_contest):
        """没有候选角色时，返回提示"""
        Candidate.query.filter_by(contest_id=sample_contest.id).delete()
        db_session.commit()

        # Mock get_client 返回一个模拟客户端
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="暂无候选角色参与本届赛事。"))
        ]

        with patch('app.ai.get_client', return_value=mock_client):
            success, content, error = generate_commentary(sample_contest.id, 'qualifying')

            assert success is True
            assert content is not None
            assert error is None

    def test_commentary_cached(self, db_session, sample_contest):
        """缓存生效，第二次调用不请求 API"""
        _cache.clear()

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="这是缓存的战报内容。"))
        ]

        with patch('app.ai.get_client', return_value=mock_client):
            success1, content1, error1 = generate_commentary(sample_contest.id, 'qualifying')
            assert success1 is True
            assert content1 == "这是缓存的战报内容。"
            assert mock_client.chat.completions.create.call_count == 1

            # 第二次调用，应该从缓存读取，不调用 API
            success2, content2, error2 = generate_commentary(sample_contest.id, 'qualifying')
            assert success2 is True
            assert content2 == "这是缓存的战报内容。"
            # 确保 API 未被再次调用
            assert mock_client.chat.completions.create.call_count == 1

    def test_commentary_api_error(self, db_session, sample_contest):
        """API 报错时返回错误信息"""
        _cache.clear()

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API 服务暂时不可用")

        with patch('app.ai.get_client', return_value=mock_client):
            success, content, error = generate_commentary(sample_contest.id, 'qualifying')

            assert success is False
            assert content is None
            assert "API 服务暂时不可用" in error

    def test_commentary_contest_not_found(self, db_session):
        """赛事不存在时返回错误"""
        success, content, error = generate_commentary(99999, 'qualifying')

        assert success is False
        assert content is None
        assert "赛事不存在" in error


class TestAIPrediction:
    """测试 AI 赛事预测"""

    def test_prediction_draft_status(self, db_session, sample_contest):
        """赛事是草稿状态时，直接返回提示，不调用 API"""
        contest = sample_contest
        contest.status = 'draft'
        db_session.commit()

        success, content, error = generate_prediction(contest.id)

        assert success is True
        assert '赛事尚未开始' in content
        assert error is None

    def test_prediction_cached(self, db_session, sample_contest):
        """缓存生效，第二次调用不请求 API"""
        _cache.clear()

        sample_contest.status = 'open'
        db_session.commit()

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="这是缓存的预测内容。"))
        ]

        with patch('app.ai.get_client', return_value=mock_client):
            success1, content1, error1 = generate_prediction(sample_contest.id)
            assert success1 is True
            assert content1 == "这是缓存的预测内容。"
            assert mock_client.chat.completions.create.call_count == 1

            # 第二次调用，从缓存读取
            success2, content2, error2 = generate_prediction(sample_contest.id)
            assert success2 is True
            assert content2 == "这是缓存的预测内容。"
            assert mock_client.chat.completions.create.call_count == 1

    def test_prediction_api_error(self, db_session, sample_contest):
        """API 报错时返回错误信息"""
        _cache.clear()

        sample_contest.status = 'open'
        db_session.commit()

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API 服务暂时不可用")

        with patch('app.ai.get_client', return_value=mock_client):
            success, content, error = generate_prediction(sample_contest.id)

            assert success is False
            assert content is None
            assert "API 服务暂时不可用" in error

    def test_prediction_contest_not_found(self, db_session):
        """赛事不存在时返回错误"""
        success, content, error = generate_prediction(99999)

        assert success is False
        assert content is None
        assert "赛事不存在" in error


class TestAICache:
    """测试 AI 缓存机制"""

    def test_cache_set_and_get(self, db_session):
        """测试缓存读写"""
        _cache.clear()

        key = "test_key"
        data = "test_data"

        _set_cache(key, data)

        cached = _get_cached(key)
        assert cached == data

    def test_cache_expiry(self, db_session):
        """测试缓存过期"""
        _cache.clear()

        from datetime import datetime, timedelta
        key = "test_expire_key"
        _cache[key] = {
            'data': "过期数据",
            'expires': datetime.now() - timedelta(seconds=1)
        }

        cached = _get_cached(key)
        assert cached is None

    def test_cache_disabled(self, db_session):
        """缓存禁用时，不读取缓存"""
        _cache.clear()

        from datetime import datetime, timedelta
        key = "test_disabled"
        _cache[key] = {
            'data': "数据",
            'expires': datetime.now() + timedelta(hours=1)
        }

        with patch('app.ai.CACHE_ENABLED', False):
            cached = _get_cached(key)
            assert cached is None


class TestAIIntegration:
    """AI 与数据库集成测试（需要真实数据）"""

    def test_commentary_with_real_contest(self, db_session, sample_contest):
        """用真实赛事数据测试 AI 战报"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="这是一段模拟的 AI 战报，描述了当前赛事情况。"))
        ]

        with patch('app.ai.get_client', return_value=mock_client):
            success, content, error = generate_commentary(sample_contest.id, 'qualifying')

            assert success is True
            assert "模拟的 AI 战报" in content
            assert error is None

            # 验证 API 被调用了一次
            assert mock_client.chat.completions.create.call_count == 1

            # 验证传入的 prompt 包含赛事信息
            call_args = mock_client.chat.completions.create.call_args[1]
            messages = call_args['messages']
            user_message = messages[1]['content']
            assert "测试萌战" in user_message
            assert "候选角色数：64" in user_message
