from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.diagnosis_report import DiagnosisReport


class Resume(Base):
    __tablename__ = "resume"
    __table_args__ = (Index("ix_resume_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    raw_text: Mapped[str | None] = mapped_column(Text)
    sections: Mapped[dict | None] = mapped_column(JSON)
    parse_status: Mapped[str] = mapped_column(String(16), default="pending")
    parse_error: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    reports: Mapped[list["DiagnosisReport"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        order_by="DiagnosisReport.created_at.desc()",
    )

    @property
    def latest_report(self) -> "DiagnosisReport | None":
        """列表接口只需最新一份报告；relationship 已按时间倒序。"""
        return self.reports[0] if self.reports else None
