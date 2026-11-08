from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.resume import Resume


class DiagnosisReport(Base):
    __tablename__ = "diagnosis_report"
    __table_args__ = (
        Index("ix_report_resume_created", "resume_id", "created_at"),
        {"comment": "简历诊断报告：一次诊断一份，含维度分与问题清单"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="报告 ID，自增主键"
    )
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resume.id", ondelete="CASCADE"), comment="被诊断的简历 ID"
    )
    # jd 表尚未建立，先保留可空列；建立 jd 表后再改成外键
    jd_id: Mapped[int | None] = mapped_column(Integer, comment="目标 JD ID（暂未建表，可空）")
    has_jd: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="本次诊断是否带 JD：0 否 / 1 是"
    )
    overall_score: Mapped[int] = mapped_column(Integer, comment="总分 0-100")
    dimension_scores: Mapped[list] = mapped_column(
        JSON, comment="维度分数组，如 [{\"name\":\"项目深度\",\"score\":72}]"
    )
    issues: Mapped[list] = mapped_column(
        JSON, comment="问题清单数组：每条含维度、描述、原文引用与建议"
    )
    summary: Mapped[str] = mapped_column(Text, comment="整份报告的总结文案")
    trace: Mapped[dict | None] = mapped_column(
        JSON, comment="诊断过程记录（每步输入输出摘要），用于复盘与评估归因"
    )
    model: Mapped[str] = mapped_column(String(64), comment="生成报告的模型名")
    prompt_version: Mapped[str] = mapped_column(
        String(32), comment="prompt 版本号，用于效果对比"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="生成时间"
    )

    resume: Mapped["Resume"] = relationship(back_populates="reports")
