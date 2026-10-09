"""
动漫社官网 · 公共页面模块
====================================

本模块处理所有对客户端可见的页面

此外，本模块还注册了全局错误处理器：
400、403、404、405、413、500 均有对应的自定义页面。
"""
import os
import uuid
import requests
from datetime import timedelta, datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory, Response, abort
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .bangumi import get_subjects, search_subjects, get_subject_detail
from .ai import generate_commentary, generate_prediction
from .config import (
    NOMINATION_LIMIT,
    QUALIFYING_MAX_CANDIDATES,
    QUALIFYING_MAX_VOTES,
    QUALIFYING_MAX_PER_CANDIDATE,
    NOMINATION_IMAGE_SIZE,
    COMPRESS_QUALITY
)
from .contest_engine import (
    calc_stage_times, calc_phase, auto_activate_contest,
    run_qualifying_promotion, run_group_promotion,
    run_knockout_advance, run_final_ranking,
    prepare_group_round_data
)
from .models import db, User, Activity, Photo, Message, Reply, Contest, Nomination, ContestVote
from .utils import get_supabase, compress_image, get_or_404
from .notify import notify

public_bp = Blueprint('public', __name__)
# Bangumi 图片服务器需要的请求头
HEADERS_FOR_IMAGE = {
    'User-Agent': 'Mozilla/5.0 (compatible; nanyi-anime-club/1.0)',
    'Referer': 'https://bgm.tv/',
}


def _calc_current_phase(contest):
    """计算赛事当前 phase（投票页面用）"""
    if contest.open_at and contest.open_at.tzinfo is not None:
        contest.open_at = contest.open_at.replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
    times = calc_stage_times(contest.open_at)
    auto_activate_contest(contest, now)
    return calc_phase(contest, now, times)


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


@public_bp.route('/about/history')
def history():
    """网站发展史页面"""
    from .changelog import get_all_commits # pylint: disable=import-outside-toplevel
    commits = get_all_commits()
    return render_template('history.html', commits=commits)


@public_bp.route('/activities')
def activities():
    activities = Activity.query.order_by(Activity.date.asc()).all()
    return render_template('activities.html', activities=activities)


@public_bp.route('/gallery')
def gallery():
    supabase = get_supabase()
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
            # 防重复提交：同一用户 5 秒内发相同内容，直接忽略
            user_id = session.get('user_id')
            if user_id:
                cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)
                duplicate = Message.query.filter(
                    Message.user_id == user_id,
                    Message.content == content,
                    Message.timestamp >= cutoff
                ).first()
                if duplicate:
                    return redirect(url_for('public.board'))

            msg = Message(
                nickname=nickname,
                content=content,
                user_id=user_id
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
        user_id = session.get('user_id')

        # 防重复提交：同一用户 5 秒内发相同内容到同一留言，忽略
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)
        duplicate = Reply.query.filter(
            Reply.user_id == user_id,
            Reply.message_id == message_id,
            Reply.content == content,
            Reply.timestamp >= cutoff
        ).first()
        if duplicate:
            return redirect(url_for('public.board'))

        reply = Reply(
            nickname=nickname,
            content=content,
            message_id=message_id,
            user_id=user_id,
            parent_reply_id=int(parent_reply_id) if parent_reply_id else None
        )
        db.session.add(reply)
        db.session.commit()
        # 通知被回复的人
        msg = db.session.get(Message, message_id)
        target_user_id = None
        if parent_reply_id:
            parent = db.session.get(Reply, int(parent_reply_id))
            if parent and parent.user_id and parent.user_id != session.get('user_id'):
                target_user_id = parent.user_id
        elif msg and msg.user_id and msg.user_id != session.get('user_id'):
            target_user_id = msg.user_id

        if target_user_id:
            notify(
                target_user_id,
                f'{nickname} 回复了你',
                content[:50] + ('...' if len(content) > 50 else ''),
                notify_type='reply',
                link=url_for('public.board')
            )
            db.session.commit()
    return redirect(url_for('public.board'))


@public_bp.route('/anime_resources')
def anime_resources():
    """番剧百科（数据来自 Bangumi）"""
    return render_template('anime_guide.html')


@public_bp.route('/api/anime/cover')
def api_anime_cover():
    """代理 Bangumi 封面图，走 Vercel CDN 缓存"""
    from urllib.parse import unquote
    url = unquote(request.args.get('url', ''))

    # 白名单校验，防止 SSRF
    if not url.startswith('https://lain.bgm.tv/'):
        abort(404)

    try:
        res = requests.get(url, headers=HEADERS_FOR_IMAGE, timeout=8)
        return Response(
            res.content,
            mimetype=res.headers.get('Content-Type', 'image/jpeg'),
            headers={'Cache-Control': 'public, max-age=604800, s-maxage=604800'},
        )
    except Exception:
        abort(404)


@public_bp.route('/api/anime/list')
def api_anime_list():
    """分页拉取番剧列表"""
    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0
    sort = request.args.get('sort', 'rank')
    if sort not in ('rank', 'heat', 'score', 'date'):
        sort = 'rank'
    items = get_subjects(offset=offset, sort=sort)
    return jsonify({'items': items})


@public_bp.route('/api/anime/search')
def api_anime_search():
    keyword = (request.args.get('q') or '').strip()
    if not keyword:
        return jsonify({'items': [], 'total': 0})
    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0
    sort = request.args.get('sort', 'match')
    if sort not in ('match', 'heat', 'rank', 'score'):
        sort = 'match'
    items, total = search_subjects(keyword, offset=offset, sort=sort)
    return jsonify({'items': items, 'total': total})


@public_bp.route('/api/anime/detail/<int:subject_id>')
def api_anime_detail(subject_id):
    """拉取单个番剧的完整详情"""
    d = get_subject_detail(subject_id)
    if not d:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(d)


@public_bp.route('/members')
def members():
    users = User.query.order_by(User.registered_at.desc()).all()
    return render_template('members.html', users=users)


# ========== 萌战系统 · 前台 ==========

@public_bp.route('/contest_center')
def contest_center():
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
    for c in Contest.query.filter_by(status='draft').all():
        auto_activate_contest(c, now)
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
    # 循环处理，防止因为跳过了中间阶段而卡住
    for _ in range(8):
        # 海选 → 小组赛
        if contest.status == 'open' and now >= times['qualifying_end']:
            has_groups = contest.config and contest.config.get('female_groups')
            if not has_groups:
                run_qualifying_promotion(contest)
                flash('海选结果已公布，小组赛开始！', 'success')
                continue

        # 小组赛 → 淘汰赛
        if contest.status in ['open', 'group_stage'] and now >= times['group_round_3_result_end']:
            has_knockout = contest.config and contest.config.get('knockout_matches_female')
            if not has_knockout:
                run_group_promotion(contest)
                flash('小组赛结束，淘汰赛16强对阵已生成！', 'success')
                continue

        # 淘汰赛各轮推进
        advanced, round_name = run_knockout_advance(contest, now, times)
        if advanced:
            flash(f'淘汰赛{round_name}对阵已生成！', 'success')
            continue

        # 决赛结束 → 最终排名
        if contest.status != 'closed' and now >= times['final_result_end']:
            run_final_ranking(contest)
            flash('赛事已结束，最终排名已生成！', 'success')
            continue

        break

    # 推进后重新计算 phase（状态可能已变）
    phase = calc_phase(contest, now, times)

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

    # ============================================================
    # 7. 构建 AI 额外数据（用于结构化解说）
    # ============================================================
    extra_data = {}
    candidates_map = {c.id: c for c in candidates}

    if phase in ['group_round_1', 'group_round_2', 'group_round_3']:
        # 小组赛：传入分组数据和票数
        if group_round_results:
            female_groups = group_round_results.get('female', [])
            female_ranking = overall_ranking_female if overall_ranking_female else []

            # 构建女组数据
            female_group_data = []
            for gi, group in enumerate(female_groups):
                matches = group.get('matches', [])
                formatted_matches = []
                for m in matches:
                    formatted_matches.append({
                        'candidate1': m.get('candidate1'),
                        'candidate2': m.get('candidate2'),
                        'votes1': m.get('votes1', 0),
                        'votes2': m.get('votes2', 0),
                        'winner': m.get('winner'),
                    })
                female_group_data.append({
                    'group_name': group.get('group_name', f'{chr(65 + gi)}组'),
                    'matches': formatted_matches,
                })

            extra_data = {
                'gender': 'female',
                'groups': contest.config.get('female_groups', []) if contest.config else [],
                'group_results': female_group_data,
                'ranking': female_ranking,
                'round_info': phase
            }

    elif phase in ['knockout_16', 'knockout_8', 'knockout_4', 'final_vote']:
        # 淘汰赛：传入对阵数据
        matches_female = contest.config.get('knockout_matches_female', []) if contest.config else []

        formatted_matches = []
        for m in matches_female:
            c1 = candidates_map.get(m.get('candidate1'))
            c2 = candidates_map.get(m.get('candidate2'))
            winner = candidates_map.get(m.get('winner'))
            formatted_matches.append({
                'candidate1_name': c1.name if c1 else '已移除',
                'candidate2_name': c2.name if c2 else '已移除',
                'votes1': m.get('votes1', 0),
                'votes2': m.get('votes2', 0),
                'status': m.get('status', 'active'),
                'winner': m.get('winner'),
                'winner_name': winner.name if winner else None,
            })

        extra_data = {
            'gender': 'female',
            'matches': formatted_matches,
            'round_info': phase
        }

    return render_template('contest_detail.html',
                           contest=contest,
                           candidates=candidates,
                           phase=phase,
                           user_nomination_count=user_nomination_count,
                           nomination_end=times['nomination_end'],
                           review_end=times['review_end'],
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
                           overall_ranking_male=overall_ranking_male,
                           extra_data=extra_data)


@public_bp.route('/contest/<int:contest_id>/nominate', methods=['POST'])
def submit_nomination(contest_id):
    supabase = get_supabase()
    if not session.get('user_id'):
        flash('请先登录', 'warning')
        return redirect(url_for('auth.login'))

    contest = get_or_404(Contest, contest_id)
    if contest.status != 'open':
        flash('该赛事未开放提名', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest_id))

    count = Nomination.query.filter_by(contest_id=contest_id, user_id=session.get('user_id')).count()
    if count >= NOMINATION_LIMIT:
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
                compressed_data = compress_image(raw_data, max_size=NOMINATION_IMAGE_SIZE, quality=COMPRESS_QUALITY)

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

    candidates = contest.candidates.filter_by(gender='female').all()
    if not candidates:
        flash('暂无女组候选角色', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    user_votes = {}
    if session.get('user_id'):
        existing = ContestVote.query.filter_by(
            contest_id=contest.id,
            user_id=session.get('user_id'),
            round_number=0,
            gender='female'
        ).all()
        for v in existing:
            user_votes[v.candidate_id] = v.weight

    return render_template('contest_qualifying_vote.html',
                           contest=contest,
                           candidates=candidates,
                           phase=_calc_current_phase(contest),
                           gender='female',
                           user_votes=user_votes)


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

    # 查当前用户已投的票
    user_votes = {}
    if session.get('user_id'):
        existing = ContestVote.query.filter_by(
            contest_id=contest.id,
            user_id=session.get('user_id'),
            round_number=0,
            gender='male'
        ).all()
        for v in existing:
            user_votes[v.candidate_id] = v.weight

    return render_template('contest_qualifying_vote.html',
                           contest=contest,
                           candidates=candidates,
                           phase=_calc_current_phase(contest),
                           gender='male',
                           user_votes=user_votes)


@public_bp.route('/contest/<int:contest_id>/qualifying/submit', methods=['POST'])
def qualifying_vote_submit(contest_id):
    def fail(msg):
        return jsonify({'success': False, 'message': msg})

    if not session.get('user_id'):
        return fail('未登录')

    contest = get_or_404(Contest, contest_id)

    if contest.status != 'open':
        return fail(f'赛事未开放（当前状态：{contest.status}）')

    gender = request.form.get('gender')
    if gender not in ['female', 'male']:
        return fail(f'无效的组别（gender={gender}）')

    # 检查是否已投过
    existing = ContestVote.query.filter_by(
        contest_id=contest.id,
        user_id=session.get('user_id'),
        round_number=0,
        gender=gender
    ).first()

    if existing:
        return fail('你已经投过票了，不能重复投票')

    # 收集票数
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
        return fail('请至少投给一个角色')

    if candidate_count > QUALIFYING_MAX_CANDIDATES:
        return fail(f'最多只能投给 {QUALIFYING_MAX_CANDIDATES} 个角色（你投了 {candidate_count} 个）')

    if total_votes > QUALIFYING_MAX_VOTES:
        return fail(f'总票数不能超过 {QUALIFYING_MAX_VOTES} 票（你投了 {total_votes} 票）')

    for _, weight in votes_data.items():
        if weight > QUALIFYING_MAX_PER_CANDIDATE:
            return fail(f'每个角色最多只能投 {QUALIFYING_MAX_PER_CANDIDATE} 票')

    # 写入
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
    except IntegrityError as e:
        db.session.rollback()
        return fail(f'数据库冲突：{str(e)}')
    except Exception as e:
        db.session.rollback()
        return fail(f'写入失败：{type(e).__name__}: {str(e)}')

    return jsonify({'success': True, 'message': '投票成功'})


# ========== 小组赛投票 ==========

@public_bp.route('/contest/<int:contest_id>/group/female')
def group_vote_female(contest_id):
    """小组赛投票 - 女组"""
    contest = get_or_404(Contest, contest_id)

    if contest.status not in ['open', 'group_stage']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    groups = contest.config.get('female_groups', []) if contest.config else []
    if not groups:
        flash('女组分组尚未生成', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    candidates = {c.id: c for c in contest.candidates.all()}

    # 算当前轮次
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
    times = calc_stage_times(contest.open_at)
    round_number = None
    if now <= times['group_round_1_end']:
        round_number = 1
    elif now <= times['group_round_2_end']:
        round_number = 2
    elif now <= times['group_round_3_end']:
        round_number = 3

    # 查用户已投的对决（用 "组_场" 作 key）
    voted_matches = []
    if session.get('user_id') and round_number:
        existing = ContestVote.query.filter_by(
            contest_id=contest.id,
            user_id=session.get('user_id'),
            round_number=round_number,
            gender='female'
        ).all()
        voted_matches = [f'{v.group_index}_{v.match_index}' for v in existing]

    return render_template('contest_group_vote.html',
                           contest=contest,
                           groups=groups,
                           candidates=candidates,
                           phase=_calc_current_phase(contest),
                           gender='female',
                           round_type='group',
                           voted_matches=voted_matches)


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

    # 算当前轮次
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
    times = calc_stage_times(contest.open_at)
    round_number = None
    if now <= times['group_round_1_end']:
        round_number = 1
    elif now <= times['group_round_2_end']:
        round_number = 2
    elif now <= times['group_round_3_end']:
        round_number = 3

    # 查用户已投的对决（用 "组_场" 作 key）
    voted_matches = []
    if session.get('user_id') and round_number:
        existing = ContestVote.query.filter_by(
            contest_id=contest.id,
            user_id=session.get('user_id'),
            round_number=round_number,
            gender='male'
        ).all()
        voted_matches = [f'{v.group_index}_{v.match_index}' for v in existing]

    return render_template('contest_group_vote.html',
                           contest=contest,
                           groups=groups,
                           candidates=candidates,
                           phase=_calc_current_phase(contest),
                           gender='male',
                           round_type='group',
                           voted_matches=voted_matches)


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

    # 与 calc_phase 共用同一套时间轴，避免出现两套天数
    times = calc_stage_times(open_at)

    if now <= times['group_round_1_end']:
        round_number = 1
    elif now <= times['group_round_2_end']:
        round_number = 2
    elif now <= times['group_round_3_end']:
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
    return redirect(url_for('public.group_vote_male', contest_id=contest.id))


# ========== 淘汰赛 ==========

@public_bp.route('/contest/<int:contest_id>/knockout/female')
def knockout_vote_female(contest_id):
    """淘汰赛投票 - 女组"""
    contest = get_or_404(Contest, contest_id)

    if contest.status not in ['open', 'knockout']:
        flash('当前不可投票', 'danger')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    matches = contest.config.get('knockout_matches_female', []) if contest.config else []
    if not matches:
        flash('女组淘汰赛尚未开始', 'warning')
        return redirect(url_for('public.contest_detail', contest_id=contest.id))

    candidates = {c.id: c for c in contest.candidates.all()}

    # 算当前子轮
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
    times = calc_stage_times(contest.open_at)
    sub_round = None
    if now <= times['knockout_16_end']:
        sub_round = 1
    elif now <= times['knockout_8_end']:
        sub_round = 2
    elif now <= times['knockout_4_end']:
        sub_round = 3
    elif now <= times['final_vote_end']:
        sub_round = 4

    has_voted = False
    if session.get('user_id') and sub_round:
        has_voted = ContestVote.query.filter_by(
            contest_id=contest.id,
            user_id=session.get('user_id'),
            round_number=4,
            sub_round=sub_round,
            gender='female'
        ).first() is not None

    return render_template('contest_knockout_vote.html',
                           contest=contest,
                           matches=matches,
                           candidates=candidates,
                           phase=_calc_current_phase(contest),
                           gender='female',
                           has_voted=has_voted)


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

    # 算当前子轮
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)
    times = calc_stage_times(contest.open_at)
    sub_round = None
    if now <= times['knockout_16_end']:
        sub_round = 1
    elif now <= times['knockout_8_end']:
        sub_round = 2
    elif now <= times['knockout_4_end']:
        sub_round = 3
    elif now <= times['final_vote_end']:
        sub_round = 4

    has_voted = False
    if session.get('user_id') and sub_round:
        has_voted = ContestVote.query.filter_by(
            contest_id=contest.id,
            user_id=session.get('user_id'),
            round_number=4,
            sub_round=sub_round,
            gender= 'male'
        ).first() is not None

    return render_template('contest_knockout_vote.html',
                           contest=contest,
                           matches=matches,
                           candidates=candidates,
                           phase=_calc_current_phase(contest),
                           gender='male',
                           has_voted=has_voted)


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

    times = calc_stage_times(open_at)

    if now <= times['knockout_16_end']:
        round_name = '16强'
    elif now <= times['knockout_8_end']:
        round_name = '8强'
    elif now <= times['knockout_4_end']:
        round_name = '4强'
    elif now <= times['final_vote_end']:
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


# ========== AI 功能 ==========

@public_bp.route('/contest/<int:contest_id>/commentary')
def ai_commentary(contest_id):
    """获取 AI 实时战报"""
    phase = request.args.get('phase', '')
    force = request.args.get('force') == 'true'
    success, content, error = generate_commentary(contest_id, phase, force=force)
    if success:
        return jsonify({'success': True, 'commentary': content})
    return jsonify({'success': False, 'error': error}), 500


@public_bp.route('/contest/<int:contest_id>/predict')
def ai_predict(contest_id):
    """获取 AI 赛事预测"""
    success, content, error = generate_prediction(contest_id)
    if success:
        return jsonify({'success': True, 'prediction': content})
    return jsonify({'success': False, 'error': error}), 500


@public_bp.route('/manifest.json')
def manifest():
    club_name = os.getenv('CLUB_NAME', '动漫社')
    return jsonify({
        "name": club_name,
        "short_name": club_name,
        "description": "以热爱为名 · 共创二次元家园",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f0f8ff",
        "theme_color": "#1e2a3a",
        "orientation": "portrait",
        "icons": [
            {
                "src": "/static/images/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/images/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    })


@public_bp.route('/robots.txt')
def robots():
    return send_from_directory(os.path.join(os.path.dirname(__file__), '..', 'static'), 'robots.txt')


@public_bp.route('/sw.js')
def service_worker():
    """Service Worker 挂根路径，作用域覆盖全站。
    运行时把 CACHE_VERSION 替换为部署版本号，避免被浏览器缓存。"""
    import re
    base = os.path.join(os.path.dirname(__file__), '..')
    sw_path = os.path.join(base, 'sw.js')

    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        return 'Service Worker not found', 404

    # Vercel 会自动注入这个环境变量；本地开发时回退到 dev
    version = os.getenv('VERCEL_GIT_COMMIT_SHA', 'dev')[:8]
    content = re.sub(
        r"const CACHE_VERSION = '.*';",
        f"const CACHE_VERSION = '{version}';",
        content,
        count=1,
    )

    return Response(content, mimetype='application/javascript')


_kanban_cache = {'lines': None, 'expires': None}


@public_bp.route('/api/kanban/lines')
def api_kanban_lines():
    """返回看板娘的真实数据台词 + 闲聊池"""
    import random

    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)

    # 缓存部分：公共数据（不含用户名）
    if not (_kanban_cache['lines'] and _kanban_cache['expires'] > now):
        facts = []

        total = User.query.count()
        if total:
            facts.append(f'社团已有 {total} 位社员～')

        contest = Contest.query.filter(
            Contest.status.in_(['open', 'group_stage', 'knockout']),
            Contest.open_at <= now,
            Contest.close_at >= now
        ).order_by(Contest.created_at.desc()).first()
        if contest:
            facts.append(f'《{contest.title}》正在进行中！')

        msg = Message.query.order_by(Message.timestamp.desc()).first()
        if msg:
            snippet = msg.content[:20] + ('…' if len(msg.content) > 20 else '')
            facts.append(f'{msg.nickname}：{snippet}')

        chitchat = [
            '今天也要元气满满哦～',
            '你有多久没看番了？',
            '群里有人冒泡了吗？',
            '猜猜我几岁？',
            '网站最近更新了哦～',
            '要不要去看看照片墙？',
            '留言板有人在等你哦～',
            '听说番剧百科很好玩',
            '社长今天也辛苦了',
            '摸鱼中……勿扰',
            '我是不是站得太久了？',
            '有没有那种，好看又短的番',
            '今天天气真好啊～',
            '啊，突然想吃草莓蛋糕',
            '你点我干嘛，我很忙的（其实不忙）',
            '刚在后台看到有人上传照片了',
            '本周新番有人追吗？',
            '别看了，去发个留言吧',
            '第一次来吗？随便逛逛～',
            '我不困，我只是在打盹',
        ]

        _kanban_cache['lines'] = {'facts': facts, 'chitchat': chitchat}
        _kanban_cache['expires'] = now + timedelta(minutes=5)

    # 每次实时拼装：把"欢迎回来 XXX"放在最前
    payload = dict(_kanban_cache['lines'])
    username = session.get('username')
    if username:
        payload['facts'] = [f'欢迎回来，{username}！'] + list(payload['facts'])

    return jsonify(payload)


# 错误处理器
def page_not_found(_e):
    return render_template('404.html'), 404


def internal_server_error(_e):
    return render_template('500.html'), 500


def forbidden(_e):
    return render_template('403.html'), 403


@public_bp.app_errorhandler(405)
def method_not_allowed(_e):
    return render_template('405.html'), 405


@public_bp.app_errorhandler(400)
def bad_request(_e):
    return render_template('400.html'), 400


@public_bp.app_errorhandler(413)
def request_entity_too_large(_e):
    return render_template('413.html'), 413
