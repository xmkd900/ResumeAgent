from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.resume import Resume


class DiagnosisReport(Base):
    __tablename__ = "diagnosis_report"
    __table_args__ = (Index("ix_report_resume_created", "resume_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id", ondelete="CASCADE"))
    # jd 表尚未建立，先保留可空列；建立 jd 表后再改成外键
    jd_id: Mapped[int | None] = mapped_column(Integer)
    has_jd: Mapped[bool] = mapped_column(Boolean, default=False)
    overall_score: Mapped[int] = mapped_column(Integer)
    dimension_scores: Mapped[list] = mapped_column(JSON)
    issues: Mapped[list] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)
    trace: Mapped[dict | None] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    resume: Mapped["Resume"] = relationship(back_populates="reports")
