from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeakPointPractice(Base):
    """一次学习动作记录（修复 / 复查 / 旧版练习）。

    `kind` 区分动作类型：fix 改写缺口、review 变体题复查、legacy 旧版整题练习。
    存它是为了复盘"这条缺口到底补了几次、哪次通过"，也是复习排期的依据。
    """

    __tablename__ = "weak_point_practice"
    __table_args__ = (
        Index("ix_practice_user_time", "user_id", "created_at"),
        Index("ix_practice_point_time", "weak_point_id", "created_at"),
        {"comment": "薄弱点练习记录：问题、回答、判卷与掌握度变化"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="练习记录 ID，自增主键"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), comment="所属用户 ID"
    )
    weak_point_id: Mapped[int] = mapped_column(
        ForeignKey("weak_point.id", ondelete="CASCADE"), comment="所属薄弱点 ID"
    )
    kind: Mapped[str] = mapped_column(
        String(16), default="legacy", comment="动作类型：fix 修复 / review 复查 / legacy 旧版练习"
    )
    question_id: Mapped[int | None] = mapped_column(
        Integer, comment="题库题 ID（自拟的复述题为空）"
    )
    question: Mapped[str] = mapped_column(Text, comment="本轮练习题目")
    answer: Mapped[str] = mapped_column(Text, comment="候选人复述内容")
    verdict: Mapped[str] = mapped_column(
        String(16), comment="判卷档位：good / partial / bad"
    )
    score: Mapped[int] = mapped_column(Integer, comment="本轮得分 0-100")
    mastery_before: Mapped[int] = mapped_column(
        Integer, comment="练习前的掌握度"
    )
    mastery_after: Mapped[int] = mapped_column(
        Integer, comment="练习后的掌握度"
    )
    judgement: Mapped[dict | None] = mapped_column(
        JSON, comment="完整判卷明细：逐要点判定、命中/部分覆盖/缺失与原文引用"
    )
    gap_covered: Mapped[bool | None] = mapped_column(
        Boolean, comment="本条缺口是否补上（fix/review 的结果；legacy 为空）"
    )
    stage_before: Mapped[int | None] = mapped_column(
        Integer, comment="本次动作前的复习阶段"
    )
    stage_after: Mapped[int | None] = mapped_column(
        Integer, comment="本次动作后的复习阶段"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="练习时间"
    )
