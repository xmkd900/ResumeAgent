from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.interview_session import InterviewSession


class InterviewMessage(Base):
    __tablename__ = "interview_message"
    __table_args__ = (Index("ix_message_session_round", "session_id", "round"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_session.id", ondelete="CASCADE")
    )
    round: Mapped[int] = mapped_column(Integer, default=1)
    role: Mapped[str] = mapped_column(String(16))  # interviewer / candidate / system
    content: Mapped[str] = mapped_column(Text)

    question_id: Mapped[int | None] = mapped_column(Integer)  # 生成题可能没有题库 ID
    parent_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_message.id", ondelete="SET NULL")
    )
    depth: Mapped[int] = mapped_column(Integer, default=0)

    judgement: Mapped[dict | None] = mapped_column(JSON)
    trace: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["InterviewSession"] = relationship(back_populates="messages")
