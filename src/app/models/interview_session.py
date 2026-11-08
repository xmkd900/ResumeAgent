from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.interview_turn import InterviewTurn


class InterviewSession(Base):
    """一场面试。

    题目不再预生成：会话只保存"背景资料快照 + 预算 + 已覆盖能力"，
    下一题由面试官模型在每轮根据对话即时决定。
    """

    __tablename__ = "interview_session"
    __table_args__ = (
        Index("ix_session_user_started", "user_id", "started_at"),
        {"comment": "模拟面试会话：背景快照 + 题目预算 + 已覆盖能力"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="会话 ID，自增主键（即前端 thread 标识）"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), comment="所属用户 ID"
    )
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume.id", ondelete="SET NULL"), comment="关联简历 ID（可为空=纯 JD 面试）"
    )
    # jd 表尚未建立，先保留可空列；建立 jd 表后再改成外键
    jd_id: Mapped[int | None] = mapped_column(Integer, comment="目标 JD ID（暂未建表，可空）")
    position: Mapped[str] = mapped_column(String(64), comment="目标岗位")
    # JD 原文快照：复盘与重放需要，不能只存 jd_id
    jd_text: Mapped[str | None] = mapped_column(
        Text, comment="JD 原文快照，保证复盘时看到当时的岗位要求"
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="ongoing",
        comment="状态：ongoing 进行中 / paused 已暂停 / finished 已结束 / aborted 已中止",
    )

    # 预算：模型有权在这个区间内自行决定问几题，但不能越过上限
    max_questions: Mapped[int] = mapped_column(
        Integer, default=12, comment="题目预算硬上限，达到后强制收尾"
    )
    min_questions: Mapped[int] = mapped_column(
        Integer, default=5, comment="题目预算软下限，过早收尾会被要求继续"
    )
    asked_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="已问轮数（含追问），开场即计为 1"
    )
    asked_followups: Mapped[int] = mapped_column(
        Integer, default=0, comment="其中追问的轮数"
    )

    # 建会话时冻结的背景资料：简历要点、JD 能力项、题库能力分布
    briefing: Mapped[dict | None] = mapped_column(
        JSON,
        comment="背景快照：JD 能力项 / 简历要点 / 题库能力分布 / 简历摘要，建会话时冻结",
    )
    # 过程性统计：已覆盖能力、已问到的简历要点
    coverage: Mapped[dict | None] = mapped_column(
        JSON, comment="覆盖统计：{\"competencies\": [...], \"claim_ids\": [...]}"
    )

    evaluation: Mapped[dict | None] = mapped_column(
        JSON, comment="整场评估：分数 / 标题 / 描述 / 亮点 / 待加强 / 统计"
    )
    overall_score: Mapped[int | None] = mapped_column(
        Integer, comment="整场得分 0-100（各轮分数均值）"
    )
    summary: Mapped[str | None] = mapped_column(Text, comment="整场评语摘要")
    prompt_version: Mapped[str] = mapped_column(
        String(32), default="director-v1", comment="面试官决策 prompt 版本，用于效果对比"
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="开始时间"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="结束时间（finished 时有值）"
    )

    turns: Mapped[list["InterviewTurn"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewTurn.turn_index",
    )
