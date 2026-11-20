from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeakPoint(Base):
    """一个能力短板（跨面试累积）。

    v2 起它同时是一条"待修复的缺口"：
    - `gap_point` 保存具体缺的那一条要点，`source_turn_id` 指回原题与原话；
    - `status` 走 open → fixed → resolved，`next_review_at` 决定"今天该不该复习"；
    - `(user_id, topic)` 唯一：同题再犯只累加复发，不重复插行。
    """

    __tablename__ = "weak_point"
    __table_args__ = (
        UniqueConstraint("user_id", "topic", name="uk_weak_user_topic"),
        Index("ix_weak_user_state", "user_id", "resolved", "severity"),
        Index("ix_weak_user_review", "user_id", "status", "next_review_at"),
        {"comment": "薄弱点：跨面试累积的能力短板、复发次数与掌握度"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="薄弱点 ID，自增主键"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), comment="所属用户 ID"
    )
    topic: Mapped[str] = mapped_column(
        String(128), comment="知识点主题，同一用户内唯一（如 MySQL索引）"
    )
    domain: Mapped[str] = mapped_column(
        String(32), default="backend", comment="所属领域：backend/frontend/agent/common"
    )
    # interview / self_test
    source: Mapped[str] = mapped_column(
        String(16),
        default="interview",
        comment="来源：interview 面试暴露 / self_test 自测暴露",
    )
    # low / medium / high
    severity: Mapped[str] = mapped_column(
        String(16), default="medium", comment="严重度：low / medium / high"
    )
    relapse_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="复发次数：再次被面试判为薄弱时 +1"
    )
    mastery_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="掌握度 0-100，由练习判卷按固定公式更新（模型不直接给）",
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否已标记掌握；复发时重新置 0"
    )
    related_tags: Mapped[list | None] = mapped_column(
        JSON, comment="关联标签，用于题库练习推荐"
    )
    last_evidence: Mapped[str | None] = mapped_column(
        Text, comment="最近一次暴露的具体缺口（判卷 missing_points 或反馈摘要）"
    )
    last_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_session.id", ondelete="SET NULL"),
        comment="最近一次暴露该短板的面试会话 ID",
    )
    source_turn_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_turn.id", ondelete="SET NULL"),
        comment="缺口来源轮次：用于回放原题、原回答与原缺口",
    )
    gap_point: Mapped[str | None] = mapped_column(
        Text, comment="具体缺的那一条要点（来自判卷的缺失/部分覆盖项）"
    )
    gap_quote: Mapped[str | None] = mapped_column(
        Text, comment="候选人当时与此缺口相关的原话（可为空）"
    )
    # open 待修复 / fixed 已修复待复查 / resolved 已掌握
    status: Mapped[str] = mapped_column(
        String(16), default="open", comment="状态：open 待修复 / fixed 待复查 / resolved 已掌握"
    )
    review_stage: Mapped[int] = mapped_column(
        Integer, default=0, comment="复习阶段：0 未开始，1..N 对应 1/3/7/14/30 天"
    )
    interval_days: Mapped[int] = mapped_column(
        Integer, default=0, comment="当前复习间隔（天），SM-2 用它推算下一次"
    )
    ease_factor: Mapped[float] = mapped_column(
        Float, default=2.5, comment="SM-2 难度因子：答得好上升、答得差下降（下限 1.3）"
    )
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="下次复习时间；为空表示暂不排期"
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="最近一次复查时间"
    )
    fix_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计修复次数（改写/补一句）"
    )
    review_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计复查次数（变体题复测）"
    )
    practice_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计练习次数"
    )
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="最近一次练习时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最后更新时间",
    )
