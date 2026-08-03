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
import os
import uuid
from datetime import timedelta, datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .contest_engine import (
    calc_stage_times, calc_phase, auto_activate_contest,
    run_qualifying_promotion, run_group_promotion,
    run_knockout_advance, run_final_ranking,
    prepare_group_round_data
)
from .models import db, User, Activity, Photo, AnimeResource, Message, Reply, Contest, Nomination, ContestVote
from .utils import supabase, compress_image, get_or_404

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
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
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
    contest = get_or_404(Contest, contest_id)
    return render_template('contest_rules.html', contest=contest)


@public_bp.route('/contest/<int:contest_id>')
def contest_detail(contest_id):
    contest = get_or_404(Contest, contest_id)

    # 确保 open_at 是 naive（如果存在）
    if contest.open_at and contest.open_at.tzinfo is not None:
        contest.open_at = contest.open_at.replace(tzinfo=None)

    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)

    # 1. 计算赛程时间
    times = calc_stage_times(contest.open_at)

    # 2. 自动激活（草稿 → 开放）
    auto_activate_contest(contest, now)

    # 3. 计算当前阶段
    phase = calc_phase(contest, now, times)

    # 4. 执行自动推进

    # 海选 → 小组赛
    if phase == 'qualifying_result' and now >= times['qualifying_end'] and contest.status == 'open':
        run_qualifying_promotion(contest)
        flash('海选结果已公布，小组赛开始！', 'success')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 小组赛 → 淘汰赛
    if phase == 'group_round_3_result' and now >= times['group_round_3_result_end'] and contest.status in ['open',
                                                                                                           'group_stage']:
        run_group_promotion(contest)
        flash('小组赛结束，淘汰赛16强对阵已生成！', 'success')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 淘汰赛各轮推进
    advanced, round_name = run_knockout_advance(contest, phase, now, times)
    if advanced:
        flash(f'淘汰赛{round_name}对阵已生成！', 'success')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 决赛结束 → 最终排名
    if phase == 'final_result' and now >= times['final_result_end'] and contest.status != 'closed':
        run_final_ranking(contest)
        flash('赛事已结束，最终排名已生成！', 'success')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 5. 准备小组赛公示数据（仅当处于小组赛公示期）
    group_round_results = None
    overall_ranking_female = None
    overall_ranking_male = None

    if phase in ['group_round_1_result', 'group_round_2_result', 'group_round_3_result']:
        group_round_results, overall_ranking_female, overall_ranking_male = prepare_group_round_data(contest, phase)

    # 6. 获取数据
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
                           nomination_end=times['nomination_end'],
                           qualifying_vote_end=times['qualifying_vote_end'],
                           qualifying_end=times['qualifying_end'],
                           group_round_1_end=times['group_round_1_end'],
                           group_round_1_result_end=times['group_round_1_result_end'],
                           group_round_2_end=times['group_round_2_end'],
                           group_round_2_result_end=times['group_round_2_result_end'],
                           group_round_3_end=times['group_round_3_end'],
                           group_round_3_result_end=times['group_round_3_result_end'],
                           knockout_16_end=times['knockout_16_end'],
                           knockout_16_result_end=times['knockout_16_result_end'],
                           knockout_8_end=times['knockout_8_end'],
                           knockout_8_result_end=times['knockout_8_result_end'],
                           knockout_4_end=times['knockout_4_end'],
                           knockout_4_result_end=times['knockout_4_result_end'],
                           final_vote_end=times['final_vote_end'],
                           final_result_end=times['final_result_end'],
                           supabase_url=os.getenv('SUPABASE_URL'),
                           supabase_anon_key=os.getenv('SUPABASE_ANON_KEY'),
                           now=now,
                           current_time=now,
                           group_round_results=group_round_results,
                           overall_ranking_female=overall_ranking_female,
                           overall_ranking_male=overall_ranking_male)


@public_bp.route('/contest/<int:contest_id>/nominate', methods=['POST'])
def submit_nomination(contest_id):
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    contest = get_or_404(Contest, contest_id)
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
    contest = get_or_404(Contest, contest_id)

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
    contest = get_or_404(Contest, contest_id)

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

    contest = get_or_404(Contest, contest_id)

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
            candidate_id=candidate_id,
            user_id=session.get('user_id'),
            weight=weight,
            round_number=0,
            gender=gender
        )
        db.session.add(vote)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(
                {'error': True, 'message': f'{"女组" if gender == "female" else "男组"}投票冲突，请勿重复提交'}), 400
        flash(f'{"女组" if gender == "female" else "男组"}投票冲突，请勿重复提交', 'warning')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': '投票成功'})

    flash(f'{"女组" if gender == "female" else "男组"}投票成功！', 'success')
    if gender == 'female':
        return redirect(url_for('public.qualifying_vote_female', contest_id=contest.id))
    else:
        return redirect(url_for('public.qualifying_vote_male', contest_id=contest.id))


# ========== 小组赛投票 ==========

@public_bp.route('/contest/<int:contest_id>/group/female')
def group_vote_female(contest_id):
    """小组赛投票 - 女组"""
    contest = get_or_404(Contest, contest_id)

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
    contest = get_or_404(Contest, contest_id)

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

    contest = get_or_404(Contest, contest_id)

    if contest.status not in ['open', 'group_stage']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
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

    candidate_id = request.form.get('candidate_id')
    if not candidate_id:
        flash('请选择你要支持的角色', 'danger')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))
    candidate_id = int(candidate_id)

    # 获取该角色所在组和本轮配对
    groups = contest.config.get(f'{gender}_groups', [])
    if not groups:
        flash('分组数据不存在', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    # 找到角色所在组及组索引
    target_group_index = None
    target_group = None
    for gi, group in enumerate(groups):
        if candidate_id in group:
            target_group_index = gi
            target_group = group
            break

    if target_group is None or target_group_index is None:
        flash('该角色不在任何分组中', 'danger')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    # 确定该轮该组的配对
    if round_number == 1:
        pairs = [(target_group[0], target_group[1]), (target_group[2], target_group[3])]
    elif round_number == 2:
        pairs = [(target_group[0], target_group[2]), (target_group[1], target_group[3])]
    else:  # round_number == 3
        pairs = [(target_group[0], target_group[3]), (target_group[1], target_group[2])]

    # 找到该角色属于第几场对决
    match_index = None
    for mi, (cid1, cid2) in enumerate(pairs, start=1):
        if candidate_id == cid1 or candidate_id == cid2:
            match_index = mi
            break

    if match_index is None:
        flash('该角色当前轮次无比赛', 'danger')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    # 检查该用户当前轮次是否已投过该场对决（任意一方）
    existing = ContestVote.query.filter_by(
        contest_id=contest.id,
        user_id=session.get('user_id'),
        round_number=round_number,
        gender=gender,
        match_index=match_index,
        group_index=target_group_index
    ).first()

    if existing:
        flash(f'第{round_number}轮{"女组" if gender == "female" else "男组"}该场对决已投过票', 'warning')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    # 检查该用户当前轮次是否已投过该角色（防止重复投同一角色）
    existing_candidate = ContestVote.query.filter_by(
        contest_id=contest.id,
        user_id=session.get('user_id'),
        round_number=round_number,
        candidate_id=candidate_id,
        gender=gender
    ).first()

    if existing_candidate:
        flash('该角色本轮已投过票', 'warning')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    vote = ContestVote(
        contest_id=contest.id,
        candidate_id=candidate_id,
        user_id=session.get('user_id'),
        weight=1,
        round_number=round_number,
        gender=gender,
        match_index=match_index,
        group_index=target_group_index
    )
    db.session.add(vote)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': True,
                            'message': f'第{round_number}轮{"女组" if gender == "female" else "男组"}投票冲突，请勿重复提交'}), 400
        flash(f'第{round_number}轮{"女组" if gender == "female" else "男组"}投票冲突，请勿重复提交', 'warning')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': '投票成功'})

    flash(f'第{round_number}轮{"女组" if gender == "female" else "男组"}投票成功！', 'success')
    if gender == 'female':
        return redirect(url_for('public.group_vote_female', contest_id=contest.id))
    else:
        return redirect(url_for('public.group_vote_male', contest_id=contest.id))


# ========== 淘汰赛 ==========

@public_bp.route('/contest/<int:contest_id>/knockout/female')
def knockout_vote_female(contest_id):
    """淘汰赛投票 - 女组"""
    contest = get_or_404(Contest, contest_id)

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
    contest = get_or_404(Contest, contest_id)

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

    contest = get_or_404(Contest, contest_id)

    if contest.status not in ['open', 'knockout']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
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

    sub_round_map = {
        '16强': 1,
        '8强': 2,
        '4强': 3,
        '决赛': 4
    }
    sub_round = sub_round_map.get(round_name, 0)

    # 检查该用户当前轮次是否已投过该组别（增加 sub_round 过滤）
    existing = ContestVote.query.filter_by(
        contest_id=contest.id,
        user_id=session.get('user_id'),
        round_number=4,
        sub_round=sub_round,  # 关键：按当前子轮过滤
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
        candidate_id=int(candidate_id),
        user_id=session.get('user_id'),
        weight=1,
        round_number=4,
        sub_round=sub_round,
        gender=gender
    )
    db.session.add(vote)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': True,
                            'message': f'{round_name}{"女组" if gender == "female" else "男组"}投票冲突，请勿重复提交'}), 400
        flash(f'{round_name}{"女组" if gender == "female" else "男组"}投票冲突，请勿重复提交', 'warning')
        return redirect(request.referrer or url_for('public.contest_detail', contest_id=contest.id))

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': '投票成功'})

    flash(f'{round_name}{"女组" if gender == "female" else "男组"}投票成功！', 'success')
    if gender == 'female':
        return redirect(url_for('public.knockout_vote_female', contest_id=contest.id))
    else:
        return redirect(url_for('public.knockout_vote_male', contest_id=contest.id))


# ========== API ==========

@public_bp.route('/api/votes/<int:candidate_id>')
def api_votes(candidate_id):
    """获取某个候选人的总票数"""
    from .models import Candidate
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return {'error': 'Candidate not found'}, 404
    total = ContestVote.query.filter_by(candidate_id=candidate_id).with_entities(
        db.func.sum(ContestVote.weight)
    ).scalar() or 0
    return {'total_votes': total}


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
