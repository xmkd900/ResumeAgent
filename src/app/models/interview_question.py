from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class InterviewQuestion(Base):
    """题库主数据；Qdrant 只是它的派生索引。"""

    __tablename__ = "interview_question"
    __table_args__ = (
        Index("ix_question_pool", "domain", "competency", "status", "difficulty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(32))  # backend / frontend / agent / common
    position: Mapped[str] = mapped_column(String(64), default="")
    topic: Mapped[str] = mapped_column(String(64))
    competency: Mapped[str] = mapped_column(String(64))
    question_type: Mapped[str] = mapped_column(String(16), default="concept")
    difficulty: Mapped[str] = mapped_column(String(16), default="mid")

    content: Mapped[str] = mapped_column(Text)
    expected_points: Mapped[list | None] = mapped_column(JSON)
    rubric: Mapped[dict | None] = mapped_column(JSON)
    followup_chain: Mapped[list | None] = mapped_column(JSON)
    probe_dimensions: Mapped[list | None] = mapped_column(JSON)
    max_depth: Mapped[int] = mapped_column(Integer, default=2)

    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual / ai / import
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft / published / retired
    version: Mapped[int] = mapped_column(Integer, default=1)
    tags: Mapped[list | None] = mapped_column(JSON)
    stats: Mapped[dict | None] = mapped_column(JSON)  # 曝光/均分/区分度，后续校准
    embedding_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
