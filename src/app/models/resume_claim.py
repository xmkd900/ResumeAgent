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
    __table_args__ = (
        Index("ix_claim_resume_type", "resume_id", "claim_type"),
        {"comment": "简历可追问事实：面试出题与追证据的来源"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="事实 ID，自增主键"
    )
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resume.id", ondelete="CASCADE"), comment="所属简历 ID"
    )
    claim_type: Mapped[str] = mapped_column(
        String(16), comment="类型：project 项目 / experience 经历 / skill 技能 / metric 指标"
    )
    title: Mapped[str] = mapped_column(String(255), comment="事实标题（项目名、技能名等）")
    evidence_quote: Mapped[str] = mapped_column(
        Text, comment="简历原文引用，必须能在 raw_text 中找到，用于防止编造"
    )
    tech_tags: Mapped[list | None] = mapped_column(
        JSON, comment="涉及的技术标签数组，如 [\"MySQL\",\"Redis\"]"
    )
    metrics: Mapped[dict | None] = mapped_column(
        JSON, comment="量化指标键值对，如 {\"qps\": 3000}"
    )
    role: Mapped[str | None] = mapped_column(
        String(128), comment="承担的角色，如 后端开发 / 负责人"
    )
    confidence: Mapped[float] = mapped_column(
        Float, default=0.0, comment="抽取置信度 0-1，选题时按此排序"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="抽取时间"
    )

    resume: Mapped["Resume"] = relationship(back_populates="claims")
