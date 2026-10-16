from app.ai import generate_commentary, generate_prediction, _get_cached, _set_cache, _cache
from app.models import Candidate, ContestVote
from unittest.mock import patch, MagicMock


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
            assert "女组" in user_message
            assert "男组" in user_message


# ========== 内部 prompt 构建函数 ==========
from app.ai import _build_group_prompt, _build_knockout_prompt, _build_qualifying_prompt


class TestAIPromptBuilders:

    def test_build_group_prompt(self, sample_contest, db_session):
        # 用真实的 candidate 对象
        cands = sample_contest.candidates.filter_by(gender='female').limit(2).all()
        assert len(cands) >= 2

        extra_data = {
            'gender': 'female',
            'groups': [[cands[0].id, cands[1].id]],
            'group_results': [
                {
                    'group_name': 'A组',
                    'matches': [
                        {
                            'candidate1': cands[0],
                            'candidate2': cands[1],
                            'votes1': 10,
                            'votes2': 5,
                            'winner': None,
                        }
                    ]
                }
            ],
            'ranking': [{'name': cands[0].name, 'points': 3}],
        }
        prompt = _build_group_prompt(sample_contest, 'group_round_1', extra_data)
        assert '小组赛第1轮' in prompt
        assert '【女组】' in prompt
        assert 'A组' in prompt
        assert cands[0].name in prompt

    def test_build_knockout_prompt(self, sample_contest):
        extra_data = {
            'gender': 'female',
            'matches': [
                {'candidate1_name': 'K1', 'candidate2_name': 'K2',
                 'votes1': 8, 'votes2': 6, 'status': 'active'}
            ]
        }
        prompt = _build_knockout_prompt(sample_contest, 'knockout_16', extra_data)
        assert '女组 16强' in prompt
        assert 'K1' in prompt
        assert 'K2' in prompt


# ========== 小组赛解说（曾经只会回「数据加载中」占位） ==========
from app.ai import _auto_group_extra_data


class TestAICommentaryGroupStage:
    """小组赛 AI 解说：投票期与公示期都必须产出真实 prompt（男女组都覆盖）"""

    def _setup_group(self, sample_contest, db_session, sample_user):
        f = sample_contest.candidates.filter_by(gender='female').limit(4).all()
        m = sample_contest.candidates.filter_by(gender='male').limit(4).all()
        for c in f + m:
            c.stage = 'group_stage'
        sample_contest.config = {
            'female_groups': [[f[0].id, f[1].id, f[2].id, f[3].id]],
            'male_groups': [[m[0].id, m[1].id, m[2].id, m[3].id]],
        }
        f[3].banned = True  # f2 vs f3：f3 禁赛，f2 不战而胜
        # 第1轮票数：f0 5票胜 f1 3票；m1 7票胜 m0 2票
        for cand, weight in [(f[0], 5), (f[1], 3), (m[0], 2), (m[1], 7)]:
            db_session.add(ContestVote(
                contest_id=sample_contest.id, candidate_id=cand.id,
                user_id=sample_user.id, weight=weight,
                round_number=1, gender=cand.gender
            ))
        db_session.commit()
        return f, m

    def _mock_client(self, text='这是一段小组赛战报。'):
        client = MagicMock()
        client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=text))
        ]
        return client

    def test_vote_phase_commentary_uses_real_group_data(self, sample_contest, db_session, sample_user):
        """投票期 /commentary 不带 extra_data：解说必须自建数据而非回占位文案"""
        _cache.clear()
        f, m = self._setup_group(sample_contest, db_session, sample_user)
        mock = self._mock_client()

        with patch('app.ai.get_client', return_value=mock):
            success, content, error = generate_commentary(sample_contest.id, 'group_round_1')

        assert success is True and content == '这是一段小组赛战报。'
        user_message = mock.chat.completions.create.call_args[1]['messages'][1]['content']
        assert '小组赛第1轮' in user_message
        assert '【女组】' in user_message and '【男组】' in user_message
        assert f[0].name in user_message and f[1].name in user_message
        assert m[1].name in user_message
        assert '🏆' in user_message            # 票数胜者有标记
        assert '不战而胜' in user_message        # 禁赛判负有标注
        assert '总积分排名' in user_message      # 积分榜进入 prompt

    def test_result_phase_commentary(self, sample_contest, db_session, sample_user):
        """公示期同样产出真实 prompt"""
        _cache.clear()
        f, m = self._setup_group(sample_contest, db_session, sample_user)
        mock = self._mock_client()

        with patch('app.ai.get_client', return_value=mock):
            success, content, error = generate_commentary(sample_contest.id, 'group_round_1_result')

        assert success is True and content == '这是一段小组赛战报。'
        user_message = mock.chat.completions.create.call_args[1]['messages'][1]['content']
        assert '第1轮公示' in user_message
        assert f[0].name in user_message and m[0].name in user_message

    def test_no_groups_returns_placeholder_without_api(self, sample_contest, db_session):
        """连分组都没有（小组赛未开始/无入围）：友好占位且不打付费 API"""
        _cache.clear()

        mock = MagicMock()
        with patch('app.ai.get_client', return_value=mock):
            success, content, error = generate_commentary(sample_contest.id, 'group_round_1')

        assert success is True
        assert '数据加载中' in content
        assert mock.chat.completions.create.call_count == 0

    def test_auto_extra_data_covers_both_genders(self, sample_contest, db_session, sample_user):
        """_auto_group_extra_data 按性别分节，round_info 供缓存键使用"""
        f, m = self._setup_group(sample_contest, db_session, sample_user)

        data = _auto_group_extra_data(sample_contest, 'group_round_1')

        assert data['round_info'] == 'group_round_1'
        assert data['female']['group_results'] and data['male']['group_results']
        fr = data['female']['group_results'][0]
        assert fr['group_name'] == 'A组'
        pairs = fr['matches']
        assert pairs[0]['winner'] == f[0].id        # f0 5票 > f1 3票
        assert pairs[1]['winner'] == f[2].id        # f3 禁赛，f2 不战而胜
