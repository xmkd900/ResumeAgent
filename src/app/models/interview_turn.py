from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.interview_session import InterviewSession


class InterviewTurn(Base):
    """一轮问答是面试的唯一事实：问了什么、为什么问、怎么答、怎么判。

    这里刻意不存"整卷计划"。真实面试的下一题依赖上一轮回答，
    预生成列表会让顺序和深度都变成常量。
    """

    __tablename__ = "interview_turn"
    __table_args__ = (
        Index("ix_turn_session_index", "session_id", "turn_index"),
        Index("ix_turn_question", "question_id"),
        {"comment": "面试单轮问答：问题、决策理由、回答与判卷结果"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="轮次 ID，自增主键"
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_session.id", ondelete="CASCADE"), comment="所属面试会话 ID"
    )
    turn_index: Mapped[int] = mapped_column(
        Integer, comment="轮次序号，从 1 开始；追问也占一轮"
    )

    # open / ask / followup / legacy（旧版计划式会话回溯时标记）
    action: Mapped[str] = mapped_column(
        String(16),
        default="ask",
        comment="本轮动作：open 开场 / ask 换话题 / followup 追问 / legacy 旧版回填",
    )
    # resume / jd / bank / generated
    source: Mapped[str] = mapped_column(
        String(16),
        default="generated",
        comment="题目来源：resume 简历 / jd 岗位要求 / bank 题库 / generated 现场生成",
    )
    parent_turn_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_turn.id", ondelete="SET NULL"),
        comment="追问所指向的上一轮 ID（仅 followup 有值）",
    )
    depth: Mapped[int] = mapped_column(
        Integer, default=0, comment="追问深度：0 为新话题，每追一层 +1"
    )

    competency: Mapped[str] = mapped_column(
        String(64), default="", comment="本轮考察的能力项"
    )
    question: Mapped[str] = mapped_column(Text, comment="面试官实际说出的问题")
    rationale: Mapped[str | None] = mapped_column(
        Text, comment="为什么问这一句（模型给出的理由，仅用于复盘与调 prompt）"
    )
    expected_points: Mapped[list | None] = mapped_column(
        JSON, comment="本轮好回答应覆盖的要点，判卷依据之一"
    )
    rubric: Mapped[dict | None] = mapped_column(
        JSON, comment="判卷标准；题库题取库里的 rubric，现场生成题可为空"
    )
    question_id: Mapped[int | None] = mapped_column(
        Integer, comment="题库溯源：对应 interview_question.id，现场生成题为空"
    )
    claim_id: Mapped[int | None] = mapped_column(
        Integer, comment="简历溯源：对应 resume_claim.id，简历题有值"
    )
    review_weak_point_id: Mapped[int | None] = mapped_column(
        Integer,
        comment="本轮是复查哪条缺口（面试闭环回写用；不加外键，避免与 weak_point.source_turn_id 形成循环依赖）",
    )

    answer: Mapped[str | None] = mapped_column(Text, comment="候选人回答；为空表示正在等待作答")
    judgement: Mapped[dict | None] = mapped_column(
        JSON, comment="判卷明细：verdict/score/命中要点/缺口/追问建议/反馈"
    )
    verdict: Mapped[str | None] = mapped_column(
        String(16), comment="判卷档位：good 扎实 / partial 基本到位 / bad 需要补强"
    )
    score: Mapped[int | None] = mapped_column(Integer, comment="本轮得分 0-100")
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, comment="作答时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="提问时间"
    )

    session: Mapped["InterviewSession"] = relationship(back_populates="turns")
