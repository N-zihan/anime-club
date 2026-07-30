"""
南平一中动漫社官网 · 数据库模型定义
======================================

本模块使用 SQLAlchemy ORM 定义了网站的所有数据表结构：

用户表 (User)：
    社员信息，包含用户名、QQ号、密码哈希、头像（二进制）、
    注册时间、运营/站长身份标识。

留言表 (Message) 与回复表 (Reply)：
    构成留言板的双向数据模型，支持嵌套回复。

活动表 (Activity)：
    社团活动记录，包含标题、日期、内容描述。

番剧资源表 (AnimeResource)：
    社员推荐的番剧资源，包含标题、描述、链接、提取码、
    提交人（外键关联 User）、审核状态。

照片表 (Photo)：
    活动照片记录，存储文件名（实际文件在 Supabase Storage），
    可关联到具体活动或作为往期活动照片。

所有模型均使用 UTC 时间存储，显示时转换为东八区。
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    qq = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    registered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    avatar = db.Column(db.LargeBinary, nullable=True)
    avatar_mime = db.Column(db.String(50), nullable=True)
    is_staff = db.Column(db.Boolean, default=False)
    is_owner = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=False, default='匿名')
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', backref='messages')


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)


class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=False, default='匿名')
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    message = db.relationship('Message', backref=db.backref('replies', lazy='dynamic', order_by='Reply.timestamp'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', backref='replies')

    parent_reply_id = db.Column(db.Integer, db.ForeignKey('reply.id'), nullable=True)
    parent_reply = db.relationship('Reply', remote_side=[id], backref=db.backref('children', lazy='dynamic'))


class AnimeResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    link = db.Column(db.String(500), nullable=False)
    extract_code = db.Column(db.String(50))
    upload_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', backref='anime_resources')
    status = db.Column(db.String(20), default='pending')


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=True)
    activity = db.relationship('Activity', backref='photos')
    upload_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    uploader = db.Column(db.String(50))


# ========== 萌战系统 ==========

class Contest(db.Model):
    __tablename__ = 'contests'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), nullable=False, default='saimoe')
    gender_mode = db.Column(db.String(10), nullable=False, default='separate')
    status = db.Column(db.String(20), nullable=False, default='draft')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    open_at = db.Column(db.DateTime, nullable=True)
    close_at = db.Column(db.DateTime, nullable=True)
    config = db.Column(db.JSON, nullable=True)

    creator = db.relationship('User', backref='created_contests')
    nominations = db.relationship('Nomination', back_populates='contest', lazy='dynamic')
    candidates = db.relationship('Candidate', back_populates='contest', lazy='dynamic')
    rounds = db.relationship('ContestRound', back_populates='contest', lazy='dynamic')


class Nomination(db.Model):
    __tablename__ = 'nominations'
    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    source = db.Column(db.String(200), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='nominations')
    contest = db.relationship('Contest', back_populates='nominations')

    __table_args__ = (
        db.UniqueConstraint('contest_id', 'name', name='uq_nomination_contest_role'),
    )


class Candidate(db.Model):
    __tablename__ = 'candidates'
    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id'), nullable=False)
    nomination_id = db.Column(db.Integer, db.ForeignKey('nominations.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    source = db.Column(db.String(200), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    description = db.Column(db.Text, nullable=True)
    stage = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    contest = db.relationship('Contest', back_populates='candidates')
    nomination = db.relationship('Nomination', backref='candidate')


class ContestRound(db.Model):
    __tablename__ = 'contest_rounds'
    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id'), nullable=False)
    round_number = db.Column(db.Integer, default=1, nullable=False)
    round_type = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=True)
    start_at = db.Column(db.DateTime, nullable=True)
    end_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='pending')

    contest = db.relationship('Contest', back_populates='rounds')
    matches = db.relationship('ContestMatch', back_populates='round', lazy='dynamic')


class ContestMatch(db.Model):
    __tablename__ = 'contest_matches'
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('contest_rounds.id'), nullable=False)
    candidate1_id = db.Column(db.Integer, db.ForeignKey('candidates.id'))
    candidate2_id = db.Column(db.Integer, db.ForeignKey('candidates.id'))
    winner_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=True)
    match_order = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')

    round = db.relationship('ContestRound', back_populates='matches')
    candidate1 = db.relationship('Candidate', foreign_keys=[candidate1_id])
    candidate2 = db.relationship('Candidate', foreign_keys=[candidate2_id])
    winner = db.relationship('Candidate', foreign_keys=[winner_id])


class ContestVote(db.Model):
    __tablename__ = 'contest_votes'
    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id'), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey('contest_rounds.id'), nullable=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    weight = db.Column(db.Integer, default=1)
    round_number = db.Column(db.Integer, default=0)
    gender = db.Column(db.String(10), nullable=True)
    sub_round = db.Column(db.Integer, default=0)  # 淘汰赛子轮次
    match_index = db.Column(db.Integer, default=0)  # 小组赛同轮同组的第几场对决：1或2
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('contest_id', 'round_number', 'user_id', 'gender', 'sub_round', 'match_index',
                            name='uq_contest_vote_unique'),
    )
