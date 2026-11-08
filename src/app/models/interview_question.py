from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class InterviewQuestion(Base):
    """题库主数据；Qdrant 只是它的派生索引。"""

    __tablename__ = "interview_question"
    __table_args__ = (
        Index("ix_question_pool", "domain", "competency", "status", "difficulty"),
        {"comment": "面试题库主数据：题面、评分要点与追问线索"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="题目 ID，自增主键"
    )
    domain: Mapped[str] = mapped_column(
        String(32), comment="领域：backend 后端 / frontend 前端 / agent 智能体 / common 通用"
    )
    position: Mapped[str] = mapped_column(String(64), default="", comment="适用岗位")
    topic: Mapped[str] = mapped_column(String(64), comment="主题，如 JVM / MySQL / Redis")
    competency: Mapped[str] = mapped_column(
        String(64), comment="能力项，面试官按它判断覆盖情况"
    )
    question_type: Mapped[str] = mapped_column(
        String(16), default="concept", comment="题型：concept 概念 / scenario 场景 / project 项目 / behavioral 行为"
    )
    difficulty: Mapped[str] = mapped_column(
        String(16), default="mid", comment="难度：junior 初级 / mid 中级 / senior 高级"
    )

    content: Mapped[str] = mapped_column(Text, comment="题干")
    expected_points: Mapped[list | None] = mapped_column(
        JSON, comment="好回答应覆盖的要点数组，判卷时作为允许的缺口来源"
    )
    rubric: Mapped[dict | None] = mapped_column(
        JSON, comment="判卷标准，如 {\"must\": [...], \"bonus\": [...]}"
    )
    followup_chain: Mapped[list | None] = mapped_column(
        JSON, comment="预设追问链（供参考，实际追问由面试官现场决定）"
    )
    probe_dimensions: Mapped[list | None] = mapped_column(
        JSON, comment="可追问维度：原理 / 取舍 / 验证 / 边界 / 失败场景"
    )
    max_depth: Mapped[int] = mapped_column(
        Integer, default=2, comment="建议追问深度上限（代码硬上限为 4）"
    )

    source: Mapped[str] = mapped_column(
        String(16), default="manual", comment="来源：manual 人工 / ai 生成 / import 导入"
    )
    status: Mapped[str] = mapped_column(
        String(16), default="draft", comment="状态：draft 草稿 / published 已发布 / retired 已下线"
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, comment="版本号，题目内容变更时 +1"
    )
    tags: Mapped[list | None] = mapped_column(JSON, comment="检索标签数组")
    stats: Mapped[dict | None] = mapped_column(
        JSON, comment="使用统计：曝光次数 / 平均分 / 区分度，用于题目淘汰"
    )
    embedding_id: Mapped[str | None] = mapped_column(
        String(32), comment="Qdrant 向量 ID（题库过千后启用，可为空）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="最后更新时间"
    )
