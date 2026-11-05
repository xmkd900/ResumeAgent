from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.resume import Resume


class ResumeClaim(Base):
    """从简历中抽取出的可追问事实；evidence_quote 是生成面试题的引用依据。"""

    __tablename__ = "resume_claim"
    __table_args__ = (Index("ix_claim_resume_type", "resume_id", "claim_type"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id", ondelete="CASCADE"))
    claim_type: Mapped[str] = mapped_column(String(16))  # project / experience / skill / metric
    title: Mapped[str] = mapped_column(String(255))
    evidence_quote: Mapped[str] = mapped_column(Text)
    tech_tags: Mapped[list | None] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    role: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    resume: Mapped["Resume"] = relationship(back_populates="claims")
