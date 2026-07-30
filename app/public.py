"""
南平一中动漫社官网 · 公共页面模块
====================================

本模块处理所有对客端可见的页面（无需登录或部分需要登录）：

1. 启动页 (/) —— 带有 Canvas 波浪粒子动画的品牌页面
2. 首页 (/home) —— 卡片导航式入口
3. 社团介绍 (/about) —— 展示站长、运营团队和技术栈
4. 活动列表 (/activities) —— 按日期排序的所有活动
5. 照片墙 (/gallery) —— 按活动分类展示历史图片
6. 留言板 (/board) —— 社员自由交流，支持嵌套回复
7. 番剧资源 (/anime_resources) —— 展示已审核通过的资源
8. 番剧推荐 (/submit_anime) —— 社员提交资源，待审核
9. 社员名单 (/members) —— 展示所有注册社员

此外，本模块还注册了全局错误处理器：
400、403、404、405、413、500 均有对应的自定义页面。
"""

import io
import uuid
from datetime import timedelta, datetime, timezone

from PIL import Image
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy.orm import joinedload

from .models import db, User, Activity, Photo, AnimeResource, Message, Reply, Contest, Nomination, ContestVote, \
    Candidate
from .utils import supabase


def compress_image(file_data, max_size=(400, 400), quality=85):
    """压缩图片到指定尺寸和品质，返回压缩后的字节数据"""
    img = Image.open(io.BytesIO(file_data))
    # 转换为RGB（防止PNG透明背景问题）
    if img.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=quality, optimize=True)
    return output.getvalue()


public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def splash():
    return render_template('splash.html')


@public_bp.route('/home')
def index():
    return render_template('index.html')


@public_bp.route('/about')
def about():
    users = User.query.all()
    staff = User.query.filter_by(is_staff=True).all()
    owner = User.query.filter_by(is_owner=True).first()
    return render_template('about.html', users=users, staff=staff, owner=owner)


@public_bp.route('/activities')
def activities():
    activities = Activity.query.order_by(Activity.date.asc()).all()
    return render_template('activities.html', activities=activities)


@public_bp.route('/gallery')
def gallery():
    activities = Activity.query.options(joinedload(Activity.photos)).order_by(Activity.date.desc()).all()
    uncategorized_photos = Photo.query.filter_by(activity_id=None).all()

    for photo in uncategorized_photos:
        photo.url = supabase.storage.from_('photos').get_public_url(photo.filename)
    for activity in activities:
        for photo in activity.photos:
            photo.url = supabase.storage.from_('photos').get_public_url(photo.filename)

    return render_template('gallery.html', activities=activities, uncategorized_photos=uncategorized_photos)


@public_bp.route('/board', methods=['GET', 'POST'])
def board():
    if request.method == 'POST':
        if session.get('is_guest'):
            flash('游客不能发表留言', 'warning')
            return redirect(url_for('public.board'))
        nickname = session.get('username', '匿名')
        content = request.form.get('content')
        if content:
            msg = Message(
                nickname=nickname,
                content=content,
                user_id=session.get('user_id')
            )
            db.session.add(msg)
            db.session.commit()
        return redirect(url_for('public.board'))

    messages = db.session.query(Message).options(
        joinedload(Message.user)
    ).order_by(Message.timestamp.desc()).all()

    all_replies = Reply.query.options(
        joinedload(Reply.user),
        joinedload(Reply.parent_reply).joinedload(Reply.user)
    ).order_by(Reply.timestamp.asc()).all()

    for reply in all_replies:
        reply.timestamp = reply.timestamp + timedelta(hours=8)

    reply_dict_by_msg = {}
    for reply in all_replies:
        if reply.message_id not in reply_dict_by_msg:
            reply_dict_by_msg[reply.message_id] = []
        reply_dict_by_msg[reply.message_id].append(reply)

    for msg in messages:
        msg.timestamp = msg.timestamp + timedelta(hours=8)
        msg._replies = reply_dict_by_msg.get(msg.id, [])

    return render_template('board.html', messages=messages)


@public_bp.route('/reply/<int:message_id>', methods=['POST'])
def add_reply(message_id):
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    if session.get('is_guest'):
        flash('游客不能回复留言', 'warning')
        return redirect(url_for('public.board'))

    nickname = session.get('username', '匿名')
    content = request.form.get('content')
    parent_reply_id = request.form.get('parent_reply_id')

    if content:
        reply = Reply(
            nickname=nickname,
            content=content,
            message_id=message_id,
            user_id=session.get('user_id'),
            parent_reply_id=int(parent_reply_id) if parent_reply_id else None
        )
        db.session.add(reply)
        db.session.commit()
    return redirect(url_for('public.board'))


@public_bp.route('/anime_resources')
def anime_resources():
    resources = AnimeResource.query.filter_by(status='approved').order_by(AnimeResource.upload_time.desc()).all()
    return render_template('anime_resources.html', resources=resources)


@public_bp.route('/submit_anime', methods=['GET', 'POST'])
def submit_anime():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    if session.get('is_guest'):
        flash('游客不能推荐番剧', 'warning')
        return redirect(url_for('public.anime_resources'))
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        link = request.form.get('link')
        extract_code = request.form.get('extract_code')
        if not title or not link:
            flash('标题和链接不能为空', 'danger')
            return redirect(url_for('public.submit_anime'))
        new_resource = AnimeResource(
            title=title,
            description=description,
            link=link,
            extract_code=extract_code,
            user_id=session.get('user_id'),
            status='pending'
        )
        db.session.add(new_resource)
        db.session.commit()
        flash('提交成功，等待管理员审核', 'success')
        return redirect(url_for('public.anime_resources'))
    return render_template('submit_anime.html')


@public_bp.route('/members')
def members():
    users = User.query.order_by(User.registered_at.desc()).all()
    return render_template('members.html', users=users)


# ========== 萌战系统 · 前台 ==========

@public_bp.route('/contest_center')
def contest_center():
    now = datetime.now(timezone.utc)
    open_contests = Contest.query.filter(
        Contest.status == 'open',
        Contest.open_at <= now,
        Contest.close_at >= now
    ).order_by(Contest.created_at.desc()).all()
    upcoming_contests = Contest.query.filter(
        Contest.status == 'draft',
        Contest.open_at > now
    ).order_by(Contest.open_at.asc()).all()
    closed_contests = Contest.query.filter(
        Contest.status == 'closed'
    ).order_by(Contest.created_at.desc()).limit(10).all()
    return render_template('contest_center.html',
                           open_contests=open_contests,
                           upcoming_contests=upcoming_contests,
                           closed_contests=closed_contests)


@public_bp.route('/contest/<int:contest_id>/rules')
def contest_rules(contest_id):
    """赛事规则确认页"""
    contest = Contest.query.get_or_404(contest_id)
    return render_template('contest_rules.html', contest=contest)


@public_bp.route('/contest/<int:contest_id>')
def contest_detail(contest_id):
    contest = Contest.query.get_or_404(contest_id)
    now = datetime.now(timezone.utc)

    def set_time_to_18(dt):
        return dt.replace(hour=18, minute=0, second=0, microsecond=0)

    # ========== 访问时自动激活赛事 ==========
    if contest.status == 'draft' and contest.open_at and now >= contest.open_at:
        contest.status = 'open'
        db.session.commit()

    # ========== 计算所有阶段时间（基于开赛日） ==========
    open_at = contest.open_at
    if open_at:
        nomination_end = set_time_to_18(open_at + timedelta(days=5))
        review_end = set_time_to_18(open_at + timedelta(days=8))
        qualifying_vote_end = set_time_to_18(open_at + timedelta(days=12))
        qualifying_end = set_time_to_18(open_at + timedelta(days=13))
        group_round_1_end = set_time_to_18(open_at + timedelta(days=17))
        group_round_1_result_end = set_time_to_18(open_at + timedelta(days=18))
        group_round_2_end = set_time_to_18(open_at + timedelta(days=22))
        group_round_2_result_end = set_time_to_18(open_at + timedelta(days=23))
        group_round_3_end = set_time_to_18(open_at + timedelta(days=27))
        group_round_3_result_end = set_time_to_18(open_at + timedelta(days=28))
        knockout_16_end = set_time_to_18(open_at + timedelta(days=32))
        knockout_16_result_end = set_time_to_18(open_at + timedelta(days=33))
        knockout_8_end = set_time_to_18(open_at + timedelta(days=37))
        knockout_8_result_end = set_time_to_18(open_at + timedelta(days=38))
        knockout_4_end = set_time_to_18(open_at + timedelta(days=42))
        knockout_4_result_end = set_time_to_18(open_at + timedelta(days=43))
        final_vote_end = set_time_to_18(open_at + timedelta(days=47))
        final_result_end = set_time_to_18(open_at + timedelta(days=50))
    else:
        nomination_end = review_end = qualifying_vote_end = qualifying_end = None
        group_round_1_end = group_round_1_result_end = None
        group_round_2_end = group_round_2_result_end = None
        group_round_3_end = group_round_3_result_end = None
        knockout_16_end = knockout_16_result_end = None
        knockout_8_end = knockout_8_result_end = None
        knockout_4_end = knockout_4_result_end = None
        final_vote_end = final_result_end = None

    # ========== 判断当前阶段 ==========
    if contest.status == 'closed':
        phase = 'closed'
    elif contest.status == 'draft':
        phase = 'not_started'
    elif not open_at:
        phase = 'unknown'
    else:
        if now < open_at:
            phase = 'not_started'
        elif now < nomination_end:
            phase = 'nomination'
        elif now < review_end:
            phase = 'review'
        elif now < qualifying_vote_end:
            phase = 'qualifying'
        elif now < qualifying_end:
            phase = 'qualifying_result'
        elif now < group_round_1_end:
            phase = 'group_round_1'
        elif now < group_round_1_result_end:
            phase = 'group_round_1_result'
        elif now < group_round_2_end:
            phase = 'group_round_2'
        elif now < group_round_2_result_end:
            phase = 'group_round_2_result'
        elif now < group_round_3_end:
            phase = 'group_round_3'
        elif now < group_round_3_result_end:
            phase = 'group_round_3_result'
        elif now < knockout_16_end:
            phase = 'knockout_16'
            if contest.status != 'knockout':
                contest.status = 'knockout'
                db.session.commit()
        elif now < knockout_16_result_end:
            phase = 'knockout_16_result'
            if contest.status != 'knockout':
                contest.status = 'knockout'
                db.session.commit()
        elif now < knockout_8_end:
            phase = 'knockout_8'
            if contest.status != 'knockout':
                contest.status = 'knockout'
                db.session.commit()
        elif now < knockout_8_result_end:
            phase = 'knockout_8_result'
            if contest.status != 'knockout':
                contest.status = 'knockout'
                db.session.commit()
        elif now < knockout_4_end:
            phase = 'knockout_4'
            if contest.status != 'knockout':
                contest.status = 'knockout'
                db.session.commit()
        elif now < knockout_4_result_end:
            phase = 'knockout_4_result'
            if contest.status != 'knockout':
                contest.status = 'knockout'
                db.session.commit()
        elif now < final_vote_end:
            phase = 'final_vote'
            if contest.status != 'knockout':
                contest.status = 'knockout'
                db.session.commit()
        elif now < final_result_end:
            phase = 'final_result'
            if contest.status != 'final':
                contest.status = 'final'
                db.session.commit()
        else:
            phase = 'closed'
            if contest.status != 'closed':
                contest.status = 'closed'
                db.session.commit()

    # ========== 海选公示日结束后自动进入小组赛 ==========
    if phase == 'qualifying_result' and now >= qualifying_end and contest.status == 'open':
        import random
        from sqlalchemy import func as sa_func

        female_candidates = contest.candidates.filter_by(gender='female').all()
        male_candidates = contest.candidates.filter_by(gender='male').all()

        def count_votes(candidates):
            result = []
            for c in candidates:
                total = ContestVote.query.filter_by(candidate_id=c.id, round_id=None, round_number=0).with_entities(
                    sa_func.sum(ContestVote.weight)).scalar() or 0
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

        if contest.config is None:
            contest.config = {}
        contest.config['female_groups'] = [[c.id for c in group] for group in female_groups]
        contest.config['male_groups'] = [[c.id for c in group] for group in male_groups]
        contest.config['female_top32'] = [c.id for c in female_top32]
        contest.config['male_top32'] = [c.id for c in male_top32]
        contest.config['female_result'] = [
            {'name': item['candidate'].name, 'source': item['candidate'].source, 'votes': item['total_votes']} for item
            in female_result[:32]]
        contest.config['male_result'] = [
            {'name': item['candidate'].name, 'source': item['candidate'].source, 'votes': item['total_votes']} for item
            in male_result[:32]]

        contest.status = 'group_stage'
        db.session.commit()

        flash('海选结果已公布，小组赛开始！', 'success')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # ========== 小组赛第3轮公示结束后自动进入淘汰赛 ==========
    if phase == 'group_round_3_result' and now >= group_round_3_result_end and contest.status in ['open',
                                                                                                  'group_stage']:
        import random
        from sqlalchemy import func as sa_func

        # ---------- 1. 统计小组赛积分 ----------
        # 小组赛共3轮，每轮每人投1票，角色获得票数即为该轮得分
        # 积分规则：胜+3，平+1，负+0（票数高者胜，票数相同为平）
        # 每个小组4人，组内单循环，每组共3轮

        def get_group_stage_results(gender):
            """获取指定性别的小组赛结果，返回每个角色的积分和票数"""
            # 获取该性别所有参与小组赛的角色
            candidates = contest.candidates.filter_by(gender=gender, stage='group_stage').all()
            if not candidates:
                return [], {}

            # 获取该性别的小组分组
            groups = contest.config.get(f'{gender}_groups', [])
            if not groups:
                return [], {}

            # 统计每个角色在3轮中的得票数
            # 按 (组号, 轮次) 统计票数，然后判断胜负
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

            # 确定每个角色属于哪一组
            for gi, group in enumerate(groups):
                for cid in group:
                    if cid in result:
                        result[cid]['group_index'] = gi

            # 对每组、每轮统计票数
            for gi, group in enumerate(groups):
                # 组内4个角色
                group_candidates = [cid for cid in group if cid in result]
                if len(group_candidates) < 4:
                    continue

                # 3轮循环
                for round_num in [1, 2, 3]:
                    # 每轮两两对战：0vs1, 2vs3
                    # 实际应为：第1轮 0vs1, 2vs3；第2轮 0vs2, 1vs3；第3轮 0vs3, 1vs2
                    # 这里按对阵表生成
                    if round_num == 1:
                        pairs = [(group_candidates[0], group_candidates[1]),
                                 (group_candidates[2], group_candidates[3])]
                    elif round_num == 2:
                        pairs = [(group_candidates[0], group_candidates[2]),
                                 (group_candidates[1], group_candidates[3])]
                    else:  # round_num == 3
                        pairs = [(group_candidates[0], group_candidates[3]),
                                 (group_candidates[1], group_candidates[2])]

                    for cid1, cid2 in pairs:
                        # 统计该轮这两个角色的票数
                        votes1 = ContestVote.query.filter_by(
                            contest_id=contest.id,
                            candidate_id=cid1,
                            round_number=round_num,
                            gender=gender
                        ).with_entities(sa_func.sum(ContestVote.weight)).scalar() or 0

                        votes2 = ContestVote.query.filter_by(
                            contest_id=contest.id,
                            candidate_id=cid2,
                            round_number=round_num,
                            gender=gender
                        ).with_entities(sa_func.sum(ContestVote.weight)).scalar() or 0

                        # 累加总票数
                        result[cid1]['total_votes'] += votes1
                        result[cid2]['total_votes'] += votes2

                        # 判断胜负
                        if votes1 > votes2:
                            result[cid1]['wins'] += 1
                            result[cid2]['losses'] += 1
                        elif votes1 < votes2:
                            result[cid2]['wins'] += 1
                            result[cid1]['losses'] += 1
                        else:
                            result[cid1]['draws'] += 1
                            result[cid2]['draws'] += 1

            # 计算积分（胜+3，平+1，负+0）
            for cid, data in result.items():
                data['points'] = data['wins'] * 3 + data['draws'] * 1

            # 按组排序，返回结果
            return result, groups

        # ---------- 2. 获取男女组积分 ----------
        female_result, female_groups = get_group_stage_results('female')
        male_result, male_groups = get_group_stage_results('male')

        # ---------- 3. 每组取前2名晋级 ----------
        def get_top2_from_groups(result, groups):
            """从每个组中取积分前2名"""
            top16 = []
            for gi, group in enumerate(groups):
                # 获取该组所有角色
                group_candidates = [cid for cid in group if cid in result]
                # 按积分排序（积分相同按总票数）
                group_candidates.sort(key=lambda cid: (result[cid]['points'], result[cid]['total_votes']), reverse=True)
                # 取前2名
                top2 = group_candidates[:2]
                top16.extend(top2)
                # 更新角色状态
                for cid in top2:
                    if cid in result:
                        result[cid]['candidate'].stage = 'knockout'
            return top16

        female_top16 = get_top2_from_groups(female_result, female_groups)
        male_top16 = get_top2_from_groups(male_result, male_groups)

        # ---------- 4. 生成淘汰赛16强对阵（随机抽签） ----------
        def generate_knockout_matches(candidate_ids, gender_name):
            """生成16强对阵表（随机抽签）"""
            if len(candidate_ids) < 16:
                # 如果不足16人，补全（实际不会发生）
                return []
            # 随机打乱顺序
            shuffled = candidate_ids[:]
            random.shuffle(shuffled)
            matches = []
            for i in range(0, 16, 2):
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

        female_matches = generate_knockout_matches(female_top16, 'female')
        male_matches = generate_knockout_matches(male_top16, 'male')

        # ---------- 5. 存储到 contest.config ----------
        if contest.config is None:
            contest.config = {}
        contest.config['knockout_matches_female'] = female_matches
        contest.config['knockout_matches_male'] = male_matches
        contest.config['female_top16'] = female_top16
        contest.config['male_top16'] = male_top16

        # 更新角色状态
        for cid in female_top16:
            candidate = Candidate.query.get(cid)
            if candidate:
                candidate.stage = 'knockout'
        for cid in male_top16:
            candidate = Candidate.query.get(cid)
            if candidate:
                candidate.stage = 'knockout'

        contest.status = 'knockout'
        db.session.commit()

        flash('小组赛结束，淘汰赛16强对阵已生成！', 'success')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # ========== 获取数据 ==========
    candidates = contest.candidates.all()
    user_nomination_count = Nomination.query.filter_by(
        contest_id=contest.id,
        user_id=session.get('user_id')
    ).count() if session.get('user_id') else 0

    return render_template('contest_detail.html',
                           contest=contest,
                           candidates=candidates,
                           phase=phase,
                           user_nomination_count=user_nomination_count,
                           nomination_end=nomination_end,
                           qualifying_vote_end=qualifying_vote_end,
                           qualifying_end=qualifying_end,
                           group_round_1_end=group_round_1_end,
                           group_round_1_result_end=group_round_1_result_end,
                           group_round_2_end=group_round_2_end,
                           group_round_2_result_end=group_round_2_result_end,
                           group_round_3_end=group_round_3_end,
                           group_round_3_result_end=group_round_3_result_end,
                           knockout_16_end=knockout_16_end,
                           knockout_16_result_end=knockout_16_result_end,
                           knockout_8_end=knockout_8_end,
                           knockout_8_result_end=knockout_8_result_end,
                           knockout_4_end=knockout_4_end,
                           knockout_4_result_end=knockout_4_result_end,
                           final_vote_end=final_vote_end,
                           final_result_end=final_result_end,
                           now=now)


@public_bp.route('/contest/<int:contest_id>/nominate', methods=['POST'])
def submit_nomination(contest_id):
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    contest = Contest.query.get_or_404(contest_id)
    if contest.status != 'open':
        flash('该赛事未开放提名', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest_id))

    count = Nomination.query.filter_by(contest_id=contest_id, user_id=session.get('user_id')).count()
    if count >= 5:
        flash('你已达到提名上限（5个角色）', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest_id))

    name = request.form.get('name')
    source = request.form.get('source')
    gender = request.form.get('gender')
    description = request.form.get('description')

    if not name or not source or not gender:
        flash('角色名、作品名、性别为必填项', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest_id))

    existing = Nomination.query.filter_by(contest_id=contest_id, name=name).first()
    if existing:
        flash(f'角色 "{name}" 已被提名，不可重复', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest_id))

    # 图片上传
    image_url = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'png'
            filename = f"contest_{contest_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
            try:
                # 读取并压缩图片
                raw_data = file.read()
                compressed_data = compress_image(raw_data, max_size=(400, 400), quality=85)

                supabase.storage.from_('contest_images').upload(
                    filename,
                    compressed_data,
                    file_options={"content-type": 'image/jpeg'}  # 统一转为JPEG
                )
                image_url = supabase.storage.from_('contest_images').get_public_url(filename)
            except Exception as e:
                flash(f'图片上传失败: {str(e)}', 'danger')
                return redirect(url_for('public.contest_detail', contest_id=contest_id))

    if not image_url:
        flash('请上传角色图片', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest_id))

    nomination = Nomination(
        contest_id=contest_id,
        user_id=session.get('user_id'),
        name=name,
        source=source,
        gender=gender,
        image_url=image_url,
        description=description,
        status='pending'
    )
    db.session.add(nomination)
    db.session.commit()
    flash(f'已成功提名 "{name}"，等待管理员审核', 'success')
    return redirect(url_for('public.contest_detail', contest_id=contest_id))


# ========== 海选投票（分男女独立页面） ==========

@public_bp.route('/contest/<int:contest_id>/qualifying/female')
def qualifying_vote_female(contest_id):
    """海选投票 - 女组"""
    contest = Contest.query.get_or_404(contest_id)

    if contest.status != 'open':
        flash('该赛事未开放', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 获取女组候选角色
    candidates = contest.candidates.filter_by(gender='female').all()
    if not candidates:
        flash('暂无女组候选角色', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    return render_template('contest_qualifying_vote.html',
                           contest=contest,
                           candidates=candidates,
                           gender='female')


@public_bp.route('/contest/<int:contest_id>/qualifying/male')
def qualifying_vote_male(contest_id):
    """海选投票 - 男组"""
    contest = Contest.query.get_or_404(contest_id)

    if contest.status != 'open':
        flash('该赛事未开放', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 获取男组候选角色
    candidates = contest.candidates.filter_by(gender='male').all()
    if not candidates:
        flash('暂无男组候选角色', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    return render_template('contest_qualifying_vote.html',
                           contest=contest,
                           candidates=candidates,
                           gender='male')


@public_bp.route('/contest/<int:contest_id>/qualifying/submit', methods=['POST'])
def qualifying_vote_submit(contest_id):
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    contest = Contest.query.get_or_404(contest_id)

    if contest.status != 'open':
        flash('该赛事未开放', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    gender = request.form.get('gender')
    if gender not in ['female', 'male']:
        flash('无效的组别', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 检查该用户是否已投过该组别
    existing = ContestVote.query.filter_by(
        contest_id=contest.id,
        user_id=session.get('user_id'),
        round_number=0,
        gender=gender
    ).first()

    if existing:
        flash(f'{"女组" if gender == "female" else "男组"}已投过票，不可重复投票', 'warning')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    votes_data = {}
    total_votes = 0
    candidate_count = 0

    for key, value in request.form.items():
        if key.startswith('vote_'):
            candidate_id = int(key.split('_')[1])
            weight = int(value) if value else 0
            if weight > 0:
                votes_data[candidate_id] = weight
                total_votes += weight
                candidate_count += 1

    if not votes_data:
        flash('请至少投给一个角色', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    if candidate_count > 5:
        flash(f'{"女组" if gender == "female" else "男组"}最多只能投给5个角色', 'danger')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    if total_votes > 15:
        flash(f'{"女组" if gender == "female" else "男组"}总票数不能超过15票', 'danger')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    for cid, weight in votes_data.items():
        if weight > 3:
            flash(f'{"女组" if gender == "female" else "男组"}每个角色最多只能投3票', 'danger')
            return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    for candidate_id, weight in votes_data.items():
        vote = ContestVote(
            contest_id=contest.id,
            round_id=None,
            candidate_id=candidate_id,
            user_id=session.get('user_id'),
            weight=weight,
            round_number=0,
            gender=gender
        )
        db.session.add(vote)
    db.session.commit()

    flash(f'{"女组" if gender == "female" else "男组"}投票成功！', 'success')

    if gender == 'female':
        return redirect(url_for('public.qualifying_vote_female', contest_id=contest.id))
    else:
        return redirect(url_for('public.qualifying_vote_male', contest_id=contest.id))


# ========== 小组赛投票 ==========

@public_bp.route('/contest/<int:contest_id>/group/female')
def group_vote_female(contest_id):
    """小组赛投票 - 女组"""
    contest = Contest.query.get_or_404(contest_id)

    if contest.status not in ['open', 'group_stage']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 获取女组分组数据
    groups = contest.config.get('female_groups', []) if contest.config else []
    if not groups:
        flash('女组分组尚未生成', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 获取所有候选角色（用于显示名字）
    candidates = {c.id: c for c in contest.candidates.all()}

    return render_template('contest_group_vote.html',
                           contest=contest,
                           groups=groups,
                           candidates=candidates,
                           gender='female',
                           round_type='group')


@public_bp.route('/contest/<int:contest_id>/group/male')
def group_vote_male(contest_id):
    """小组赛投票 - 男组"""
    contest = Contest.query.get_or_404(contest_id)

    if contest.status not in ['open', 'group_stage']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 获取男组分组数据
    groups = contest.config.get('male_groups', []) if contest.config else []
    if not groups:
        flash('男组分组尚未生成', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    candidates = {c.id: c for c in contest.candidates.all()}

    return render_template('contest_group_vote.html',
                           contest=contest,
                           groups=groups,
                           candidates=candidates,
                           gender='male',
                           round_type='group')


@public_bp.route('/contest/<int:contest_id>/group/submit', methods=['POST'])
def group_vote_submit(contest_id):
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    contest = Contest.query.get_or_404(contest_id)

    if contest.status not in ['open', 'group_stage']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    now = datetime.now()
    open_at = contest.open_at
    if not open_at:
        flash('赛事开始时间未设置', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    def set_time_to_18(dt):
        return dt.replace(hour=18, minute=0, second=0, microsecond=0)

    round_1_end = set_time_to_18(open_at + timedelta(days=17))
    round_2_end = set_time_to_18(open_at + timedelta(days=22))
    round_3_end = set_time_to_18(open_at + timedelta(days=27))

    if now < round_1_end:
        round_number = 1
    elif now < round_2_end:
        round_number = 2
    elif now < round_3_end:
        round_number = 3
    else:
        flash('小组赛已结束', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    gender = request.form.get('gender')
    if gender not in ['female', 'male']:
        flash('无效的组别', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 检查该用户当前轮次是否已投过该组别
    existing = ContestVote.query.filter_by(
        contest_id=contest.id,
        user_id=session.get('user_id'),
        round_number=round_number,
        gender=gender
    ).first()

    if existing:
        flash(f'第{round_number}轮{"女组" if gender == "female" else "男组"}已投过票', 'warning')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    candidate_id = request.form.get('candidate_id')
    if not candidate_id:
        flash('请选择你要支持的角色', 'danger')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    vote = ContestVote(
        contest_id=contest.id,
        round_id=None,
        candidate_id=int(candidate_id),
        user_id=session.get('user_id'),
        weight=1,
        round_number=round_number,
        gender=gender
    )
    db.session.add(vote)
    db.session.commit()

    flash(f'第{round_number}轮{"女组" if gender == "female" else "男组"}投票成功！', 'success')

    if gender == 'female':
        return redirect(url_for('public.group_vote_female', contest_id=contest.id))
    else:
        return redirect(url_for('public.group_vote_male', contest_id=contest.id))


# ========== 淘汰赛 ==========

@public_bp.route('/contest/<int:contest_id>/knockout/female')
def knockout_vote_female(contest_id):
    """淘汰赛投票 - 女组"""
    contest = Contest.query.get_or_404(contest_id)

    if contest.status not in ['open', 'knockout']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 获取淘汰赛对阵
    matches = contest.config.get('knockout_matches_female', []) if contest.config else []
    if not matches:
        flash('女组淘汰赛尚未开始', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    candidates = {c.id: c for c in contest.candidates.all()}

    return render_template('contest_knockout_vote.html',
                           contest=contest,
                           matches=matches,
                           candidates=candidates,
                           gender='female')


@public_bp.route('/contest/<int:contest_id>/knockout/male')
def knockout_vote_male(contest_id):
    """淘汰赛投票 - 男组"""
    contest = Contest.query.get_or_404(contest_id)

    if contest.status not in ['open', 'knockout']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    matches = contest.config.get('knockout_matches_male', []) if contest.config else []
    if not matches:
        flash('男组淘汰赛尚未开始', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    candidates = {c.id: c for c in contest.candidates.all()}

    return render_template('contest_knockout_vote.html',
                           contest=contest,
                           matches=matches,
                           candidates=candidates,
                           gender='male')


@public_bp.route('/contest/<int:contest_id>/knockout/submit', methods=['POST'])
def knockout_vote_submit(contest_id):
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    contest = Contest.query.get_or_404(contest_id)

    if contest.status not in ['open', 'knockout']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    now = datetime.now()
    open_at = contest.open_at
    if not open_at:
        flash('赛事开始时间未设置', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    def set_time_to_18(dt):
        return dt.replace(hour=18, minute=0, second=0, microsecond=0)

    knockout_16_end = set_time_to_18(open_at + timedelta(days=32))
    knockout_8_end = set_time_to_18(open_at + timedelta(days=37))
    knockout_4_end = set_time_to_18(open_at + timedelta(days=42))
    knockout_final_end = set_time_to_18(open_at + timedelta(days=47))

    if now < knockout_16_end:
        round_name = '16强'
    elif now < knockout_8_end:
        round_name = '8强'
    elif now < knockout_4_end:
        round_name = '4强'
    elif now < knockout_final_end:
        round_name = '决赛'
    else:
        flash('淘汰赛已结束', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    gender = request.form.get('gender')
    if gender not in ['female', 'male']:
        flash('无效的组别', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 检查该用户当前轮次是否已投过该组别
    existing = ContestVote.query.filter_by(
        contest_id=contest.id,
        user_id=session.get('user_id'),
        round_number=4,
        gender=gender
    ).first()

    if existing:
        flash(f'{round_name}{"女组" if gender == "female" else "男组"}已投过票', 'warning')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    candidate_id = request.form.get('candidate_id')
    if not candidate_id:
        flash('请选择你要支持的角色', 'danger')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    vote = ContestVote(
        contest_id=contest.id,
        round_id=None,
        candidate_id=int(candidate_id),
        user_id=session.get('user_id'),
        weight=1,
        round_number=4,
        gender=gender
    )
    db.session.add(vote)
    db.session.commit()

    flash(f'{round_name}{"女组" if gender == "female" else "男组"}投票成功！', 'success')

    if gender == 'female':
        return redirect(url_for('public.knockout_vote_female', contest_id=contest.id))
    else:
        return redirect(url_for('public.knockout_vote_male', contest_id=contest.id))


# 错误处理器
def page_not_found(e):
    return render_template('404.html'), 404


def internal_server_error(e):
    return render_template('500.html'), 500


def forbidden(e):
    return render_template('403.html'), 403


@public_bp.app_errorhandler(405)
def method_not_allowed(e):
    return render_template('405.html'), 405


@public_bp.app_errorhandler(400)
def bad_request(e):
    return render_template('400.html'), 400


@public_bp.app_errorhandler(413)
def request_entity_too_large(e):
    return render_template('413.html'), 413
