"""面试上下文与题库检索。

这里只回答两个问题：
1. 这位候选人/这个岗位的背景是什么（简历要点、诊断薄弱维度、能力目录）；
2. 给定一句检索意图，题库里哪些题最相关。

**不做排题**。排题属于面试官（`interview_director`），因为它依赖上一轮回答。
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field

import jieba
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


# --------------------------------------------------------------------------- #
# 题库检索：BM25F（字段加权）+ 相关度阈值 + 可观测的降级
# --------------------------------------------------------------------------- #
# 字段权重：题干是主信号，能力项次之，topic/tags 辅助。
# `expected_points` 刻意不参与检索——它是评分标准而不是检索特征，且长度通常是
# 题干的 2-3 倍，会把 BM25 的长度归一化带偏。实测去掉后归一化召回 0.822 → 0.880。
FIELD_WEIGHTS: dict[str, float] = {
    "content": 3.0,
    "competency": 2.0,
    "topic": 1.0,
    "tags": 1.0,
}

# 检索停用词：疑问/语气/泛动词。中文查询里这些词占比很高，不剔除会让
# "如何做红烧肉" 命中一堆"你会怎么做"的题（实测未剔除时仍返回 2 条无关题）。
STOPWORDS: frozenset[str] = frozenset(
    {
        "如何", "怎么", "怎样", "什么", "哪些", "哪个", "为什么", "是否",
        "可以", "应该", "需要", "一般", "通常", "分别", "区别", "介绍",
        "讲讲", "说说", "谈谈", "聊聊", "一下", "这个", "那个", "这些",
        "那些", "我们", "你们", "他们", "自己", "以及", "或者", "还有",
        "做", "用", "有", "是", "在", "和", "与", "或", "的", "了",
        "吗", "呢", "吧", "啊", "会", "要", "能", "把", "被", "让",
        "你", "我", "他", "她", "它", "请", "问", "然后", "之后",
    }
)

# 领域词：domain 已经把候选限定在某个领域内，这些词没有区分度。
# 保留它们会让"前端内存泄漏"把只含"前端"的监控/懒加载题排到第 2-5 位。
DOMAIN_TERMS: frozenset[str] = frozenset(
    {"前端", "后端", "服务端", "后台", "agent", "智能体", "开发"}
)

# 查询词覆盖率下限：低于它说明只是撞上了几个泛词，不是真相关。
# 由 20 条金标 + 5 条无关查询做参数扫描选出：0.5 会丢掉 41% 的金标题，
# 0.25 时归一化召回 0.870、无关查询基本拦得住（0.2 会把"swiftui 动画"
# 这类弱相关查询也放进来）。绝对 BM25 分数不可跨库移植，所以阈值按覆盖率定。
MIN_QUERY_COVERAGE = 0.25
# 相对分数下限：低于 top1 该比例的候选视为噪声。
RELATIVE_SCORE_FLOOR = 0.2
# BM25 参数：k1 控制词频饱和速度，b 控制长度归一化强度。
BM25_K1 = 1.5
BM25_B = 0.75


@dataclass(slots=True)
class SearchOutcome:
    """一次检索的完整结果：除了题目，还告诉调用方"这次是不是降级了"。

    降级指结构化过滤没能满足（能力项不存在、难度没有对应题），此时返回的题
    可能偏离意图。调用方可以选择不用，而不是像以前那样无从判断。
    """

    questions: list[InterviewQuestion] = field(default_factory=list)
    degraded: bool = False
    # 考点不在题库：候选与意图无关，调用方应弃用（改走现场出题）
    competency_missed: bool = False
    # 难度不存在：题目内容仍相关，只是难度档不符，可保留但需知情
    difficulty_missed: bool = False
    reasons: list[str] = field(default_factory=list)
    top_score: float = 0.0
    filtered_out: int = 0


def _normalize(text: str) -> str:
    """文本规范化：去掉空白并转小写，用于能力项名称比对。"""
    return re.sub(r"\s+", "", (text or "")).lower()


def _terms(text: str) -> list[str]:
    """检索用切词：在 tokenize 基础上去停用词与纯标点。

    单字保留（"锁""栈""堆"本身就是技术词），靠 IDF 压制无意义单字。
    """
    return [
        token
        for token in tokenize(text)
        if token not in STOPWORDS
        and token not in DOMAIN_TERMS
        and re.search(r"[0-9a-z\u4e00-\u9fff]", token)
    ]


def _field_tokens(question: InterviewQuestion) -> dict[str, list[str]]:
    """按字段分别切词：加权要在词频层面做，不能靠把字段拼成一坨。"""
    return {
        "content": _terms(question.content or ""),
        "competency": _terms(question.competency or ""),
        "topic": _terms(question.topic or ""),
        "tags": _terms(" ".join(str(tag) for tag in (question.tags or []))),
    }


def rank_by_bm25f(
    questions: list[InterviewQuestion],
    query: str,
    *,
    weights: dict[str, float] | None = None,
) -> tuple[dict[int, float], dict[int, float]]:
    """BM25F：字段加权词频 + 统一 IDF + 加权长度归一化。

    与"把字段拼成一个字符串再跑 BM25"的区别：
    - 加权作用在词频上，不靠重复字符串（重复会拉长文档，反被长度惩罚抵消）；
    - 只对配置了权重的字段计分，评分标准类字段不参与。

    Returns:
        (分数表, 查询词覆盖率表)，key 均为题目 id。
    """
    weight_map = weights or FIELD_WEIGHTS
    query_tokens = _terms(query)
    terms = list(dict.fromkeys(query_tokens))
    if not questions or not terms:
        return {}, {}

    docs = [_field_tokens(question) for question in questions]
    total = len(docs)

    # 文档频率：同一篇文档内重复出现只计一次
    doc_freq: Counter[str] = Counter()
    for fields in docs:
        seen: set[str] = set()
        for name, tokens in fields.items():
            if weight_map.get(name, 0.0) > 0:
                seen.update(tokens)
        doc_freq.update(seen)

    weighted_lengths = [
        sum(
            len(tokens) * weight_map.get(name, 0.0)
            for name, tokens in fields.items()
        )
        for fields in docs
    ]
    avg_length = sum(weighted_lengths) / max(1, len(weighted_lengths))

    scores: dict[int, float] = {}
    coverage: dict[int, float] = {}
    for question, fields, length in zip(questions, docs, weighted_lengths):
        weighted_tf: Counter[str] = Counter()
        for name, tokens in fields.items():
            weight = weight_map.get(name, 0.0)
            if weight <= 0:
                continue
            for token in tokens:
                weighted_tf[token] += weight

        score = 0.0
        hit = 0
        for term in terms:
            tf = weighted_tf.get(term, 0.0)
            if tf <= 0:
                continue
            hit += 1
            freq = doc_freq.get(term, 0)
            idf = math.log(1 + (total - freq + 0.5) / (freq + 0.5))
            norm = BM25_K1 * (
                1 - BM25_B + BM25_B * length / max(avg_length, 1e-9)
            )
            score += idf * tf * (BM25_K1 + 1) / (tf + norm)

        scores[question.id] = score
        coverage[question.id] = hit / len(terms)
    return scores, coverage


def _filter_relevance(
    questions: list[InterviewQuestion],
    scores: dict[int, float],
    coverage: dict[int, float],
    *,
    min_coverage: float = MIN_QUERY_COVERAGE,
    relative_floor: float = RELATIVE_SCORE_FLOOR,
) -> tuple[list[InterviewQuestion], float, int]:
    """按覆盖率与相对分数过滤候选。

    绝对 BM25 分数依赖语料规模与 idf 分布，不可跨库移植，所以这里用
    "查询词覆盖率"做硬门槛、"相对 top1"做软门槛，避免写死一个分数。
    """
    if not questions:
        return [], 0.0, 0
    top = max((scores.get(question.id, 0.0) for question in questions), default=0.0)
    if top <= 0:
        return [], 0.0, len(questions)

    kept: list[InterviewQuestion] = []
    for question in questions:
        score = scores.get(question.id, 0.0)
        if score <= 0:
            continue
        if coverage.get(question.id, 0.0) < min_coverage:
            continue
        if score < top * relative_floor:
            continue
        kept.append(question)

    kept.sort(key=lambda question: (-scores.get(question.id, 0.0), question.id))
    return kept, top, len(questions) - len(kept)


def search_bank_outcome(
    db: Session,
    *,
    domain: str,
    query: str = "",
    competency: str | None = None,
    difficulty: str | None = None,
    exclude_ids: set[int] | None = None,
    limit: int = 5,
    strict: bool = False,
    min_coverage: float = MIN_QUERY_COVERAGE,
) -> SearchOutcome:
    """检索题库并返回降级信息（推荐调用方用这个，而不是只看题目列表）。

    Args:
        strict: 结构化过滤无匹配时是否直接返回空。False 表示回退到更大范围并
            在 `reasons` 里说明；True 表示宁可没有候选，让调用方改走其他策略
            （例如让面试官现场出题），避免硬塞一道不相关的题。
    """
    exclude = exclude_ids or set()
    pool = [item for item in load_question_pool(db, domain) if item.id not in exclude]
    if not pool:
        return SearchOutcome([], True, ["题库为空或候选已被全部排除"])

    reasons: list[str] = []
    degraded = False
    competency_missed = False
    difficulty_missed = False

    if competency:
        target = _normalize(competency)
        exact = [item for item in pool if _normalize(item.competency) == target]
        if exact:
            pool = exact
        else:
            fuzzy = [
                item
                for item in pool
                if target
                and (
                    target in _normalize(item.competency)
                    or _normalize(item.competency) in target
                )
            ]
            if fuzzy:
                pool = fuzzy
                degraded = True
                reasons.append(
                    f"能力项「{competency}」未精确命中，按包含匹配取 {len(fuzzy)} 道"
                )
            else:
                degraded = True
                competency_missed = True
                reasons.append(f"能力项「{competency}」在题库中不存在，已回退到全部能力项")
                if strict:
                    return SearchOutcome([], degraded=True, competency_missed=True, reasons=reasons)

    if difficulty:
        matched = [item for item in pool if item.difficulty == difficulty]
        if matched:
            pool = matched
        else:
            degraded = True
            difficulty_missed = True
            available = sorted({item.difficulty for item in pool if item.difficulty})
            reasons.append(
                f"没有 {difficulty} 难度的题（现有 {available}），已回退到全部难度"
            )
            if strict:
                return SearchOutcome([], degraded=True, competency_missed=competency_missed, difficulty_missed=True, reasons=reasons)

    if not (query or "").strip():
        return SearchOutcome(
            pool[:limit],
            degraded=degraded,
            competency_missed=competency_missed,
            difficulty_missed=difficulty_missed,
            reasons=reasons,
        )

    scores, coverage = rank_by_bm25f(pool, query)
    kept, top_score, dropped = _filter_relevance(
        pool, scores, coverage, min_coverage=min_coverage
    )
    if not kept:
        return SearchOutcome(
            [],
            degraded=True,
            competency_missed=competency_missed,
            difficulty_missed=difficulty_missed,
            reasons=reasons
            + [
                (
                    f"查询与 {len(pool)} 道候选都不相关"
                    f"（查询词覆盖率 < {min_coverage:.0%}）"
                )
            ],
            top_score=top_score,
            filtered_out=len(pool),
        )
    return SearchOutcome(
        kept[:limit],
        degraded=degraded,
        competency_missed=competency_missed,
        difficulty_missed=difficulty_missed,
        reasons=reasons,
        top_score=top_score,
        filtered_out=dropped,
    )


def search_bank(
    db: Session,
    *,
    domain: str,
    query: str = "",
    competency: str | None = None,
    difficulty: str | None = None,
    exclude_ids: set[int] | None = None,
    limit: int = 5,
    strict: bool = False,
) -> list[InterviewQuestion]:
    """题库检索工具：先结构化过滤，再 BM25F 排序，最后按相关度过滤。

    只返回题目列表；需要知道是否降级请改用 `search_bank_outcome`。
    """
    return search_bank_outcome(
        db,
        domain=domain,
        query=query,
        competency=competency,
        difficulty=difficulty,
        exclude_ids=exclude_ids,
        limit=limit,
        strict=strict,
    ).questions


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
