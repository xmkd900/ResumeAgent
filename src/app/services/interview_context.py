"""面试上下文与题库检索。

这里只回答两个问题：
1. 这位候选人/这个岗位的背景是什么（简历要点、诊断薄弱维度、能力目录）；
2. 给定一句检索意图，题库里哪些题最相关。

**不做排题**。排题属于面试官（`interview_director`），因为它依赖上一轮回答。
"""

import re

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DiagnosisReport, InterviewQuestion, Resume, ResumeClaim

FRONTEND_KEYWORDS = ("前端", "frontend", "vue", "react")
AGENT_KEYWORDS = ("agent", "大模型", "llm", "ai开发", "ai 开发", "智能体")
BACKEND_KEYWORDS = ("后端", "backend", "java", "python", "后台", "服务端")

# 简历摘要优先取这些板块
EXCERPT_SECTIONS = ("projects", "experience", "education", "skills", "awards")
EXCERPT_LIMIT = 1600


class ContextError(Exception):
    """上下文无法装配（简历缺失/未解析）时抛出，由 API 层转 404/409。"""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def resolve_domain(position: str) -> str:
    """岗位 → 题库领域。未知岗位按后端处理，common 题始终参与。
    
    Args:
        position: 岗位名称，如"前端工程师"、"Java后端"、"AI开发"
    
    Returns:
        题库领域标识："frontend"、"backend"、"agent"、"common"
    """
    text = (position or "").strip().lower()
    if text in {"ai", "人工智能"}:
        return "agent"
    for keyword in FRONTEND_KEYWORDS:
        if keyword in text:
            return "frontend"
    for keyword in AGENT_KEYWORDS:
        if keyword in text:
            return "agent"
    for keyword in BACKEND_KEYWORDS:
        if keyword in text:
            return "backend"
    return "backend"


def load_owned_resume(db: Session, resume_id: int, user_id: int) -> Resume:
    """按 id 访问必须带 user_id，防越权。
    
    Args:
        db: 数据库会话
        resume_id: 简历ID
        user_id: 用户ID
    
    Returns:
        Resume对象
    
    Raises:
        ContextError: 简历不存在或无权限
    """
    resume = db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    if resume is None:
        raise ContextError("简历不存在", 404)
    return resume


def load_claims(db: Session, resume_id: int) -> list[ResumeClaim]:
    """加载简历的结构化声明（claims）。没有 claims 是合法状态（纯题库/JD 出题），不抛异常。
    
    Args:
        db: 数据库会话
        resume_id: 简历ID
    
    Returns:
        简历声明列表，按置信度降序排列
    """
    return list(
        db.scalars(
            select(ResumeClaim)
            .where(ResumeClaim.resume_id == resume_id)
            .order_by(ResumeClaim.confidence.desc(), ResumeClaim.id)
        ).all()
    )


def load_weak_dimensions(db: Session, resume_id: int) -> list[str]:
    """从最近诊断报告取 <70 的维度；没有报告就返回空列表。
    
    Args:
        db: 数据库会话
        resume_id: 简历ID
    
    Returns:
        薄弱维度名称列表，如["并发", "数据库"]
    """
    report = db.scalar(
        select(DiagnosisReport)
        .where(DiagnosisReport.resume_id == resume_id)
        .order_by(DiagnosisReport.created_at.desc())
        .limit(1)
    )
    if report is None:
        return []

    weak: list[str] = []
    for item in report.dimension_scores or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        score = item.get("score")
        if name and isinstance(score, (int, float)) and score < 70:
            weak.append(str(name))
    return weak


def resume_excerpt(resume: Resume | None) -> str:
    """给模型看的简历摘要：优先结构化板块，其次原文截断。
    
    Args:
        resume: 简历对象
    
    Returns:
        简历摘要文本，最多1600字符
    """
    if resume is None:
        return ""
    sections = resume.sections or {}
    if isinstance(sections, dict):
        lines: list[str] = []
        for key in EXCERPT_SECTIONS:
            for line in sections.get(key) or []:
                text = str(line).strip()
                if text:
                    lines.append(text)
        joined = "\n".join(lines)
        if joined:
            return joined[:EXCERPT_LIMIT]
    return (resume.raw_text or "")[:EXCERPT_LIMIT]


def load_question_pool(db: Session, domain: str) -> list[InterviewQuestion]:
    """加载题库，只取 published 状态；目标 domain + common 兜底。
    
    Args:
        db: 数据库会话
        domain: 题库领域（frontend/backend/agent/common）
    
    Returns:
        题库题目列表
    """
    domains = ["common"] if domain == "common" else [domain, "common"]
    return list(
        db.scalars(
            select(InterviewQuestion)
            .where(
                InterviewQuestion.domain.in_(domains),
                InterviewQuestion.status == "published",
            )
            .order_by(InterviewQuestion.id)
        ).all()
    )


def competency_catalog(db: Session, domain: str) -> list[dict]:
    """题库能力分布：让面试官知道"还有哪些方向可以考"。
    
    Args:
        db: 数据库会话
        domain: 题库领域
    
    Returns:
        能力分布列表，每项包含：
        - competency: 能力名称
        - count: 题目数量
        - types: 题目类型集合
        按题目数量降序排列
    """
    counter: dict[str, dict] = {}
    for question in load_question_pool(db, domain):
        competency = (question.competency or "").strip()
        if not competency:
            continue
        entry = counter.setdefault(
            competency, {"competency": competency, "count": 0, "types": set()}
        )
        entry["count"] += 1
        entry["types"].add(question.question_type or "concept")
    rows = [
        {
            "competency": item["competency"],
            "count": item["count"],
            "types": sorted(item["types"]),
        }
        for item in counter.values()
    ]
    return sorted(rows, key=lambda row: (-row["count"], row["competency"]))


def tokenize(text: str) -> list[str]:
    """使用 jieba 分词，返回小写且去空白的 token 列表。
    
    Args:
        text: 待分词文本
    
    Returns:
        token 列表
    """
    return [token.strip().lower() for token in jieba.lcut(text or "") if token.strip()]


def _question_text(question: InterviewQuestion) -> str:
    """提取问题的所有文本字段，用于 BM25 检索。
    
    Args:
        question: 题库题目
    
    Returns:
        合并后的文本字符串
    """
    return " ".join(
        [
            question.content or "",
            question.competency or "",
            question.topic or "",
            " ".join(question.tags or []),
            " ".join(question.expected_points or []),
        ]
    )


def rank_by_bm25(questions: list[InterviewQuestion], query: str) -> dict[int, float]:
    """使用 BM25 算法对题目进行相关性排序。
    
    Args:
        questions: 题目列表
        query: 检索查询词
    
    Returns:
        字典，key为题目ID，value为BM25分数
    """
    if not questions:
        return {}
    corpus = [tokenize(_question_text(question)) for question in questions]
    if not any(corpus):
        return {question.id: 0.0 for question in questions}
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokenize(query))
    return {question.id: float(score) for question, score in zip(questions, scores)}


def _normalize(text: str) -> str:
    """文本规范化：去除空白并转小写。
    
    Args:
        text: 原始文本
    
    Returns:
        规范化后的文本
    """
    return re.sub(r"\s+", "", (text or "")).lower()


def search_bank(
    db: Session,
    *,
    domain: str,
    query: str = "",
    competency: str | None = None,
    difficulty: str | None = None,
    exclude_ids: set[int] | None = None,
    limit: int = 5,
) -> list[InterviewQuestion]:
    """题库检索工具：先结构化过滤，再 BM25 排序。
    
    Args:
        db: 数据库会话
        domain: 题库领域
        query: 检索查询词
        competency: 能力维度过滤（可选）
        difficulty: 难度过滤（可选）
        exclude_ids: 排除的题目ID（可选）
        limit: 返回数量上限
    
    Returns:
        相关题目列表，按相关性降序
    """
    exclude = exclude_ids or set()
    pool = [q for q in load_question_pool(db, domain) if q.id not in exclude]
    if not pool:
        return []

    if competency:
        target = _normalize(competency)
        exact = [q for q in pool if _normalize(q.competency) == target]
        fuzzy = [
            q
            for q in pool
            if target and (target in _normalize(q.competency) or _normalize(q.competency) in target)
        ]
        pool = exact or fuzzy or pool

    if difficulty:
        matched = [q for q in pool if q.difficulty == difficulty]
        pool = matched or pool

    if not (query or "").strip():
        return pool[:limit]

    scores = rank_by_bm25(pool, query)
    ranked = sorted(pool, key=lambda q: (-scores.get(q.id, 0.0), q.id))
    return ranked[:limit]


def question_brief(question: InterviewQuestion) -> dict:
    """给模型看的候选题摘要；不含内部统计字段。
    
    Args:
        question: 题库题目
    
    Returns:
        题目摘要字典，包含：
        - id: 题目ID
        - competency: 能力维度
        - difficulty: 难度
        - type: 题目类型
        - question: 问题内容
        - expected_points: 期望得分点（最多5条）
    """
    return {
        "id": question.id,
        "competency": question.competency,
        "difficulty": question.difficulty,
        "type": question.question_type,
        "question": question.content,
        "expected_points": list(question.expected_points or [])[:5],
    }
