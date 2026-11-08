from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.diagnosis_report import DiagnosisReport
    from app.models.resume_claim import ResumeClaim


class Resume(Base):
    __tablename__ = "resume"
    __table_args__ = (
        Index("ix_resume_user_created", "user_id", "created_at"),
        {"comment": "简历文件与解析结果"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="简历 ID，自增主键"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), comment="所属用户 ID"
    )
    filename: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    file_path: Mapped[str] = mapped_column(
        String(512), comment="服务器存储路径（含 PII，不对外暴露）"
    )
    file_size: Mapped[int] = mapped_column(Integer, default=0, comment="文件大小，单位字节")
    raw_text: Mapped[str | None] = mapped_column(Text, comment="解析出的简历全文")
    sections: Mapped[dict | None] = mapped_column(
        JSON, comment="分节结果：education/experience/projects/skills/awards/other 的句子数组"
    )
    parse_status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        comment="解析状态：pending 待解析 / done 成功 / failed 失败",
    )
    parse_error: Mapped[str | None] = mapped_column(
        String(255), comment="解析失败原因（parse_status=failed 时有值）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="上传时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="最后更新时间"
    )

    reports: Mapped[list["DiagnosisReport"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        order_by="DiagnosisReport.created_at.desc()",
    )
    claims: Mapped[list["ResumeClaim"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        order_by="ResumeClaim.id",
    )

    @property
    def latest_report(self) -> "DiagnosisReport | None":
        """列表接口只需最新一份报告；relationship 已按时间倒序。"""
        return self.reports[0] if self.reports else None
