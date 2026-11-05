from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.interview_message import InterviewMessage


class InterviewSession(Base):
    __tablename__ = "interview_session"
    __table_args__ = (Index("ix_session_user_started", "user_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resume.id", ondelete="SET NULL"))
    # jd 表尚未建立，先保留可空列；建立 jd 表后再改成外键
    jd_id: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[str] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16), default="ongoing")  # ongoing/finished/aborted
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    current_index: Mapped[int] = mapped_column(Integer, default=0)  # 0-based
    current_depth: Mapped[int] = mapped_column(Integer, default=0)

    question_plan: Mapped[dict | None] = mapped_column(JSON)
    overall_score: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    messages: Mapped[list["InterviewMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewMessage.round",
    )
