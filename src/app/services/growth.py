"""成长闭环：薄弱点沉淀、练习推荐与掌握度更新。

三条边界（与 ARCHITECTURE ③ 一致）：

1. **薄弱点只从面试来**：练习判卷只更新 `mastery_score`，绝不新建薄弱点
   （否则"练得越多、弱项越多"，推荐权重会失真）；
2. **掌握度是算出来的**：模型只负责判这一段复述好不好，
   `mastery = 旧值 × 0.6 + 本次得分 × 0.4` 由本模块确定性计算；
3. **讲解必须有来源**：练习视图的每条 `[n]` 都指向真实题库题目，
   模型只能使用给定的资料，编号越界会被清理。
"""

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.client import LLMError, chat
from app.llm.json import extract_json_object
from app.models import (
    InterviewQuestion,
    InterviewSession,
    InterviewTurn,
    WeakPoint,
    WeakPointPractice,
)
from app.schemas.growth import (
    ExerciseOut,
    ExerciseSourceOut,
    FixResultOut,
    GapCardOut,
    GapSourceOut,
    PracticeContentOut,
    PracticeResultOut,
    QueueStatsOut,
    ReviewQuestionOut,
    ReviewResultOut,
    WeakPointExercisesOut,
    WeakPointOut,
    WeakPointQueueOut,
    WeakPointStatsOut,
)
from app.schemas.interview import JudgementOut
from app.services.interview_context import resolve_domain, tokenize
from app.services.interview_judge import JudgeError, judge_answer

logger = logging.getLogger(__name__)

WEAK_SCORE_THRESHOLD = 60  # 低于这个分数才沉淀为薄弱点
MAX_WEAK_PER_SESSION = 3  # 一场面试最多沉淀 3 个，避免刷屏
MASTERY_ALPHA = 0.4  # 新证据权重：一次练习能明显推动掌握度，但不会被单次波动带偏
RELAPSE_MASTERY_CAP = 30  # 复发时把掌握度压回"需要重新证明"的水平
# SM-2：间隔由上次间隔 × ease 推算，最长 30 天，避免复查负担失控
MAX_INTERVAL_DAYS = 30
DEFAULT_EASE = 2.5
MIN_EASE = 1.3
FIRST_INTERVAL_DAYS = 1
STATUS_OPEN = "open"
STATUS_FIXED = "fixed"
STATUS_RESOLVED = "resolved"
GENERIC_TOPICS = {"自我介绍", "自我介绍与项目深度", "项目深度", "综合", "综合能力"}

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}
SEVERITY_LABEL = {"low": "低", "medium": "中", "high": "高"}

_TYPE_LABEL = {
    "concept": "概念讲解",
    "scenario": "场景练习",
    "project": "项目追问",
    "behavioral": "行为面",
}
_TYPE_MINUTES = {"concept": 8, "scenario": 12, "project": 10, "behavioral": 8}

# 题库没有匹配题时的复述标准：不假装有标准答案，只要求讲清三件事
FREE_PRACTICE_POINTS = [
    "讲清它是什么、解决什么问题",
    "说清前提与边界：什么情况下不适用",
    "给出一个具体场景或取舍理由",
]

SYSTEM_PROMPT = """你是一个擅长改写编程问题提问的专家。把给定的问题进行改写，
可以加条件或改变约束，但不能改变原题的意思。
只输出 JSON，不要 markdown，格式：{"question": "改写后的问题"}"""



class GrowthError(Exception):
    """成长闭环业务异常；status_code 供 API 层透传。"""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


# --------------------------------------------------------------------------- #
# 薄弱点沉淀
# --------------------------------------------------------------------------- #
def _initial_mastery(score: int) -> int:
    """面试得分 → 初始掌握度。

    面试 50 分对应 30%：能听懂问题、但讲不扎实；
    不从 0 开始是为了让进度条有信息量，也不虚高。
    """
    return max(5, min(60, round(score * 0.6)))


def _severity_for(score: int) -> str:
    if score < 45:
        return "high"
    if score < 55:
        return "medium"
    return "low"


def _tags_for(db: Session, turn: InterviewTurn) -> list[str]:
    """标签优先取题库题目标签，现场生成题退化为能力项。"""
    tags: list[str] = []
    if turn.question_id is not None:
        question = db.get(InterviewQuestion, turn.question_id)
        if question is not None:
            tags.extend(str(item) for item in (question.tags or []) if str(item).strip())
            if question.competency:
                tags.append(question.competency)
    if turn.competency:
        tags.append(turn.competency)
    unique: list[str] = []
    for tag in tags:
        if tag not in unique:
            unique.append(tag)
    return unique[:8]


def _merge_tags(old: list | None, new: list[str]) -> list[str]:
    merged = [str(item) for item in (old or [])]
    for tag in new:
        if tag not in merged:
            merged.append(tag)
    return merged[:8]


def _gap_of(turn: InterviewTurn) -> tuple[str | None, str | None]:
    """从判卷结果里取"最该修的那一条"缺口及其原话。

    优先缺失项，其次部分覆盖；quote 从 point_results 里取，
    这样缺口卡能同时展示"缺什么"和"你当时怎么说的"。
    """
    judgement = turn.judgement or {}
    missing = [str(item) for item in (judgement.get("missing_points") or []) if str(item)]
    partial = [str(item) for item in (judgement.get("partial_points") or []) if str(item)]
    gap = (missing or partial or [None])[0]
    if not gap:
        return None, None
    quote = ""
    for row in judgement.get("point_results") or []:
        if str(row.get("point") or "") == gap and str(row.get("quote") or "").strip():
            quote = str(row["quote"]).strip()
            break
    return gap, quote or None


def _evidence_of(turn: InterviewTurn) -> str:
    judgement = turn.judgement or {}
    missing = [str(item) for item in (judgement.get("missing_points") or []) if str(item)]
    partial = [str(item) for item in (judgement.get("partial_points") or []) if str(item)]
    parts: list[str] = []
    if missing:
        parts.append(f"没讲到：{'、'.join(missing[:2])}")
    if partial:
        parts.append(f"只讲了一半：{'、'.join(partial[:2])}")
    if parts:
        return "；".join(parts)
    feedback = str(judgement.get("feedback") or "").strip()
    return feedback[:200] or "这一轮回答没有讲到关键细节"


def _candidate_turns(turns: list[InterviewTurn]) -> list[InterviewTurn]:
    """筛出值得沉淀的轮次：有回答、不是开场、分数低于阈值。"""
    rows = [
        turn
        for turn in turns
        if turn.answer
        and not turn.review_weak_point_id  # 复查轮由 apply_interview_reviews 处理，不重复沉淀
        and turn.action != "open"
        and (turn.score if turn.score is not None else 100) < WEAK_SCORE_THRESHOLD
        and (turn.competency or "").strip()
        and (turn.competency or "").strip() not in GENERIC_TOPICS
    ]
    # 同一能力项只取最差那一轮：一场面试不该把同一知识点记两次
    by_topic: dict[str, InterviewTurn] = {}
    for turn in rows:
        topic = (turn.competency or "").strip()[:128]
        current = by_topic.get(topic)
        if current is None or (turn.score or 0) < (current.score or 0):
            by_topic[topic] = turn
    ordered = sorted(by_topic.values(), key=lambda turn: (turn.score or 0, turn.turn_index))
    return ordered[:MAX_WEAK_PER_SESSION]


def sync_from_interview(
    db: Session,
    session: InterviewSession,
    turns: list[InterviewTurn],
    *,
    count_relapse: bool = True,
) -> dict[str, int]:
    """从一场刚结束的面试里沉淀薄弱点。

    - 正常收尾：`count_relapse=True`，同题再犯累加复发；
    - 历史回填：`count_relapse=False`，只补缺失的行，不动已有掌握度
      （否则跑一次回填脚本就会把所有人的薄弱点标成"又犯了一次"）。

    不 commit：由收尾事务统一提交，避免"评估写了一半"。
    """
    created = 0
    reopened = 0
    for turn in _candidate_turns(turns):
        topic = (turn.competency or "").strip()[:128]
        score = turn.score or 0
        severity = _severity_for(score)
        evidence = _evidence_of(turn)
        gap_point, gap_quote = _gap_of(turn)
        tags = _tags_for(db, turn)
        domain = str((session.briefing or {}).get("domain") or resolve_domain(session.position))

        row = db.scalar(
            select(WeakPoint).where(
                WeakPoint.user_id == session.user_id, WeakPoint.topic == topic
            )
        )
        if row is None:
            db.add(
                WeakPoint(
                    user_id=session.user_id,
                    topic=topic,
                    domain=domain,
                    source="interview",
                    severity=severity,
                    relapse_count=0,
                    mastery_score=_initial_mastery(score),
                    resolved=False,
                    related_tags=tags,
                    last_evidence=evidence,
                    last_session_id=session.id,
                    source_turn_id=turn.id,
                    gap_point=gap_point,
                    gap_quote=gap_quote,
                    status=STATUS_OPEN,
                )
            )
            created += 1
            continue

        if not count_relapse:
            continue

        # 复发：严重度取最大、重新打开、掌握度压回"需要重新证明"的水平
        if SEVERITY_ORDER[severity] > SEVERITY_ORDER.get(row.severity, 0):
            row.severity = severity
        row.relapse_count += 1
        row.resolved = False
        row.mastery_score = min(row.mastery_score, RELAPSE_MASTERY_CAP)
        row.related_tags = _merge_tags(row.related_tags, tags)
        row.last_evidence = evidence
        row.last_session_id = session.id
        row.source_turn_id = turn.id
        row.gap_point = gap_point or row.gap_point
        row.gap_quote = gap_quote or row.gap_quote
        row.status = STATUS_OPEN
        row.review_stage = 0
        row.next_review_at = None
        reopened += 1

    if created or reopened:
        logger.info(
            "session %s 沉淀薄弱点：新增 %s，复发 %s", session.id, created, reopened
        )
    return {"created": created, "reopened": reopened}


# --------------------------------------------------------------------------- #
# 查询与统计
# --------------------------------------------------------------------------- #
def _severity_rank():
    return case(
        (WeakPoint.severity == "high", 3),
        (WeakPoint.severity == "medium", 2),
        else_=1,
    )


def list_weak_points(
    db: Session, *, user_id: int, include_resolved: bool = True
) -> list[WeakPoint]:
    statement = select(WeakPoint).where(WeakPoint.user_id == user_id)
    if not include_resolved:
        statement = statement.where(WeakPoint.resolved.is_(False))
    statement = statement.order_by(
        WeakPoint.resolved.asc(),
        _severity_rank().desc(),
        WeakPoint.relapse_count.desc(),
        WeakPoint.updated_at.desc(),
    )
    return list(db.scalars(statement).all())


def weekly_practice_count(db: Session, *, user_id: int, days: int = 7) -> int:
    since = datetime.now() - timedelta(days=days)
    return int(
        db.scalar(
            select(func.count())
            .select_from(WeakPointPractice)
            .where(
                WeakPointPractice.user_id == user_id,
                WeakPointPractice.created_at >= since,
            )
        )
        or 0
    )


def build_stats(db: Session, *, user_id: int, items: list[WeakPoint]) -> WeakPointStatsOut:
    active = [item for item in items if not item.resolved]
    avg = round(sum(item.mastery_score for item in active) / len(active)) if active else 0
    return WeakPointStatsOut(
        active=len(active),
        avg_mastery=avg,
        weekly_practices=weekly_practice_count(db, user_id=user_id),
        high_priority=len([item for item in active if item.severity == "high"]),
    )


def to_out(item: WeakPoint) -> WeakPointOut:
    return WeakPointOut.model_validate(item)


def get_owned(db: Session, *, user_id: int, weak_point_id: int) -> WeakPoint:
    row = db.scalar(
        select(WeakPoint).where(
            WeakPoint.id == weak_point_id, WeakPoint.user_id == user_id
        )
    )
    if row is None:
        raise GrowthError("薄弱点不存在", 404)
    return row


# --------------------------------------------------------------------------- #
# 练习推荐
# --------------------------------------------------------------------------- #
def _related_questions(
    db: Session, *, weak_point: WeakPoint, limit: int = 8
) -> list[InterviewQuestion]:
    """按"能力项 > 标签 > 题干关键词"给题库打分，取前 N 道。"""
    pool = list(
        db.scalars(
            select(InterviewQuestion)
            .where(InterviewQuestion.status == "published")
            .order_by(InterviewQuestion.id)
        ).all()
    )
    topic = (weak_point.topic or "").strip()
    tags = {str(item) for item in (weak_point.related_tags or [])}
    scored: list[tuple[int, InterviewQuestion]] = []
    for question in pool:
        score = 0
        competency = (question.competency or "").strip()
        if topic and competency == topic:
            score += 6
        elif topic and (topic in competency or competency in topic):
            score += 4
        if topic and topic.lower() in (question.content or "").lower():
            score += 2
        labels = {str(item) for item in (question.tags or [])}
        score += min(3, len(labels & tags))
        if score:
            scored.append((score, question))
    scored.sort(key=lambda item: (-item[0], item[1].difficulty != "mid", item[1].id))
    return [question for _, question in scored[:limit]]


def _difficulty_for(mastery: int) -> str:
    """掌握度越低，题目越基础（EduQuest 的难度映射思路）。"""
    if mastery < 40:
        return "junior"
    if mastery < 70:
        return "mid"
    return "senior"


def _exercise_of(question: InterviewQuestion, *, reason: str) -> ExerciseOut:
    return ExerciseOut(
        question_id=question.id,
        title=question.content,
        type=_TYPE_LABEL.get(question.question_type, "概念讲解"),
        difficulty=question.difficulty or "mid",
        minutes=_TYPE_MINUTES.get(question.question_type, 8),
        tags=[str(item) for item in (question.tags or [])][:4],
        reason=reason,
    )


def _sort_for_mastery(
    questions: list[InterviewQuestion], difficulty: str
) -> list[InterviewQuestion]:
    return sorted(
        questions,
        key=lambda question: (
            question.difficulty != difficulty,
            0 if question.question_type == "concept" else 1,
            question.id,
        ),
    )


def _free_exercise(weak_point: WeakPoint) -> ExerciseOut:
    return ExerciseOut(
        question_id=None,
        title=f"口述：用三句话讲清「{weak_point.topic}」的核心机制与取舍",
        type="口述练习",
        difficulty=_difficulty_for(weak_point.mastery_score),
        minutes=6,
        tags=[str(item) for item in (weak_point.related_tags or [])][:4],
        reason="题库暂时没有匹配题，先用口述题确认是否真的讲得清",
    )


def _fallback_content(
    weak_point: WeakPoint, questions: list[InterviewQuestion]
) -> PracticeContentOut:
    intro: list[str] = []
    if questions:
        points = [
            str(item)
            for item in (questions[0].expected_points or [])
            if str(item).strip()
        ][:3]
        if points:
            intro.append(
                f"题库里这块的核心要求是：{'；'.join(points)}[1]。"
                "先按这个顺序把因果讲成一条线，再补自己的例子。"
            )
    if weak_point.last_evidence:
        intro.append(
            f"上一场面试暴露的问题是：{weak_point.last_evidence}。"
            "复述时先把这一点补上，再讲边界。"
        )
    if not intro:
        intro.append(
            f"「{weak_point.topic}」这类问题，面试官通常先问是什么，"
            "再追问边界和取舍；只背结论很容易在第二层被问住。"
        )
    return PracticeContentOut(
        intro=intro[:2],
        question=f"不看上文，用三句话讲清「{weak_point.topic}」的核心机制与取舍。",
        sources=_sources_of(questions, weak_point),
    )


def _sources_of(
    questions: list[InterviewQuestion], weak_point: WeakPoint
) -> list[ExerciseSourceOut]:
    if not questions:
        return [
            ExerciseSourceOut(
                idx=1,
                title=f"薄弱点档案 · {weak_point.topic}",
                meta="来自最近一次面试判卷",
            )
        ]
    return [
        ExerciseSourceOut(
            idx=index,
            title=f"内部题库 · {question.topic or question.competency}",
            meta=f"第 {question.id} 题 · {question.difficulty}",
        )
        for index, question in enumerate(questions[:3], start=1)
    ]


class _ContentDraft(BaseModel):
    intro: list[str] = Field(default_factory=list)
    question: str = ""


CONTENT_SYSTEM_PROMPT = """你是技术面试辅导老师。根据给定资料，为候选人的薄弱点写"先讲清楚"。

规则：
1. 只能使用资料里的事实，禁止补充资料外的新知识；
2. 写 2 段，每段 60-120 字，讲清"是什么 → 为什么需要 → 边界/取舍"，口语化；
3. 需要引用时在句末标 [n]，n 必须是资料编号，最多用到 [3]；
4. 最后给一道复述题：要求"不看上文，用自己的话讲清核心取舍"，一句话，不要问多个问题；
5. 只输出 JSON，不要 markdown。

输出格式：
{"intro": ["第一段", "第二段"], "question": "复述题"}"""


def _materials(questions: list[InterviewQuestion]) -> str:
    lines: list[str] = []
    for index, question in enumerate(questions[:3], start=1):
        points = "；".join(
            str(item) for item in (question.expected_points or []) if str(item).strip()
        )
        lines.append(
            f"[{index}] 题目：{question.content}\n"
            f"    能力项：{question.competency}；难度：{question.difficulty}\n"
            f"    评分要点：{points or '（无）'}"
        )
    return "\n".join(lines)


def _clean_citations(text: str, allowed: int) -> str:
    """把越界的 [n] 去掉，避免"引用了一个不存在的来源"。"""
    def replace(match: re.Match) -> str:
        index = int(match.group(1))
        return match.group(0) if 1 <= index <= allowed else ""

    return re.sub(r"\[(\d{1,2})\]", replace, text or "")


def _generate_content(
    weak_point: WeakPoint, questions: list[InterviewQuestion]
) -> PracticeContentOut | None:
    """让模型写讲解；任何失败都返回 None，由调用方降级。"""
    if not questions or not (settings.LLM_API_KEY or "").strip():
        return None
    messages = [
        {"role": "system", "content": CONTENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"<weak_point>{weak_point.topic}</weak_point>\n"
                f"<last_evidence>{weak_point.last_evidence or '无'}</last_evidence>\n"
                f"<materials>\n{_materials(questions)}\n</materials>"
            ),
        },
    ]
    try:
        response = chat(messages, max_tokens=700, temperature=0.4)
        draft = _ContentDraft.model_validate(extract_json_object(response.content))
    except (LLMError, ValueError, TypeError, ValidationError) as exc:
        logger.warning("练习讲解生成失败，改用题库要点：%s", exc)
        return None

    sources = _sources_of(questions, weak_point)
    intro = [
        _clean_citations(str(paragraph).strip(), len(sources))[:240]
        for paragraph in draft.intro
        if str(paragraph).strip()
    ][:2]
    question = _clean_citations(draft.question, len(sources)).strip()[:300]
    if not intro or not question:
        return None
    return PracticeContentOut(intro=intro, question=question, sources=sources)


def build_exercises(
    db: Session, *, user_id: int, weak_point_id: int, with_content: bool = True
) -> WeakPointExercisesOut:
    """练习视图数据。

    with_content=False 时不调模型，只给题库推荐的 fallback 讲解——
    列表页预取用这个模式，避免"点一下左侧就烧一次 token"。
    """
    weak_point = get_owned(db, user_id=user_id, weak_point_id=weak_point_id)
    candidates = _related_questions(db, weak_point=weak_point)
    difficulty = _difficulty_for(weak_point.mastery_score)
    ordered = _sort_for_mastery(candidates, difficulty)

    exercises = [
        _exercise_of(
            question,
            reason=f"匹配「{weak_point.topic}」，难度 {question.difficulty}，对应你当前的掌握度",
        )
        for question in ordered[:4]
    ]
    if not exercises:
        exercises = [_free_exercise(weak_point)]

    content = (
        _generate_content(weak_point, ordered[:3]) if with_content else None
    ) or _fallback_content(weak_point, ordered)
    return WeakPointExercisesOut(
        weak_point=to_out(weak_point), content=content, exercises=exercises
    )


# --------------------------------------------------------------------------- #
# 练习判卷与掌握度
# --------------------------------------------------------------------------- #
def _practice_target(
    db: Session, *, weak_point: WeakPoint, question_id: int | None
) -> tuple[str, list[str], dict, int | None]:
    """确定练习题目与判卷标准；题库题以库里的 rubric 为准。"""
    if question_id is not None:
        question = db.get(InterviewQuestion, question_id)
        if question is None:
            raise GrowthError("练习题不存在", 404)
        return (
            question.content,
            [str(item) for item in (question.expected_points or []) if str(item).strip()],
            dict(question.rubric or {}),
            question.id,
        )
    return (
        f"不看上文，用三句话讲清「{weak_point.topic}」的核心机制与取舍。",
        list(FREE_PRACTICE_POINTS),
        {},
        None,
    )


def _hint_for(judgement: JudgementOut, after: int) -> str:
    if after >= 90:
        return "掌握度已到 90，可以点「标记已掌握」结束这一项"
    if judgement.verdict == "good":
        return "这块基本讲清了，再练一道不同角度的题会更稳"
    if judgement.missing_points:
        return f"下一轮重点补：{judgement.missing_points[0]}"
    return "先把讲解重读一遍，再复述一次，效果比直接背结论好"


def submit_practice(
    db: Session, *, user_id: int, weak_point_id: int, answer: str, question_id: int | None
) -> PracticeResultOut:
    weak_point = get_owned(db, user_id=user_id, weak_point_id=weak_point_id)
    question, points, rubric, resolved_question_id = _practice_target(
        db, weak_point=weak_point, question_id=question_id
    )

    try:
        judgement = judge_answer(
            question=question,
            expected_points=points,
            rubric=rubric,
            answer=answer,
            position=weak_point.domain or "",
            depth=0,
        )
    except JudgeError as exc:
        raise GrowthError(str(exc), getattr(exc, "status_code", 502)) from exc

    before = weak_point.mastery_score
    after = max(0, min(100, round(before * (1 - MASTERY_ALPHA) + judgement.score * MASTERY_ALPHA)))
    weak_point.mastery_score = after
    weak_point.practice_count += 1
    weak_point.last_practiced_at = datetime.now()

    db.add(
        WeakPointPractice(
            user_id=user_id,
            weak_point_id=weak_point.id,
            question_id=resolved_question_id,
            question=question,
            answer=answer,
            verdict=judgement.verdict,
            score=judgement.score,
            mastery_before=before,
            mastery_after=after,
            judgement=judgement.model_dump(),
        )
    )
    db.commit()
    db.refresh(weak_point)

    return PracticeResultOut(
        judgement=judgement,
        mastery_before=before,
        mastery_after=after,
        resolved=weak_point.resolved,
        hint=_hint_for(judgement, after),
        weak_point=to_out(weak_point),
    )


def resolve_weak_point(db: Session, *, user_id: int, weak_point_id: int) -> WeakPointOut:
    weak_point = get_owned(db, user_id=user_id, weak_point_id=weak_point_id)
    weak_point.mastery_score = 100
    weak_point.resolved = True
    weak_point.status = STATUS_RESOLVED
    weak_point.next_review_at = None
    db.commit()
    db.refresh(weak_point)
    return to_out(weak_point)




# --------------------------------------------------------------------------- #
# v2：缺口修复（Fix）与间隔复查（Retain）
# --------------------------------------------------------------------------- #
def _quality(covered: bool, gap_status: str, score: int) -> int:
    """SM-2 的 q（0-5）：扎实通过 5，通过 4，部分 2，没答到 1。"""
    if covered and score >= 85:
        return 5
    if covered:
        return 4
    if gap_status == "partial":
        return 2
    return 1


def _apply_review_schedule(
    weak_point: WeakPoint, *, quality: int, now: datetime
) -> tuple[int, int]:
    """按 SM-2 推进/重置复习排期，返回 (stage_before, stage_after)。

    - q>=3：interval = ceil(上次间隔 × ease)，最长 30 天；间隔到 30 且 q>=4 视为掌握；
    - q<3：回到待修复，interval=1、stage=1、不排复查（等用户先补）。
    """
    stage_before = weak_point.review_stage
    ease = float(weak_point.ease_factor or DEFAULT_EASE)

    if quality >= 3:
        previous = int(weak_point.interval_days or 0)
        if previous <= 0:
            interval = FIRST_INTERVAL_DAYS if stage_before == 0 else 3
        else:
            interval = math.ceil(previous * ease)
        interval = max(FIRST_INTERVAL_DAYS, min(MAX_INTERVAL_DAYS, interval))

        weak_point.interval_days = interval
        weak_point.review_stage = max(1, stage_before) + 1
        weak_point.status = STATUS_FIXED
        weak_point.next_review_at = now + timedelta(days=interval)
        if interval >= MAX_INTERVAL_DAYS and quality >= 4:
            weak_point.status = STATUS_RESOLVED
            weak_point.resolved = True
            weak_point.mastery_score = 100
            weak_point.next_review_at = None
    else:
        weak_point.interval_days = FIRST_INTERVAL_DAYS
        weak_point.review_stage = 1
        weak_point.status = STATUS_OPEN
        weak_point.next_review_at = None

    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    weak_point.ease_factor = round(max(MIN_EASE, ease), 2)
    return stage_before, weak_point.review_stage


def _review_difficulty(stage: int) -> str:
    """复习阶段越靠后，题目越难；基础阶段用简单题确认没忘。"""
    if stage <= 1:
        return "junior"
    if stage <= 3:
        return "mid"
    return "senior"


def _source_question_id(db: Session, weak_point: WeakPoint) -> int | None:
    if weak_point.source_turn_id is None:
        return None
    turn = db.get(InterviewTurn, weak_point.source_turn_id)
    return turn.question_id if turn is not None else None


@dataclass(slots=True)
class ReviewCandidate:
    """复查题：来自题库，或由原题改写而来（id 为空表示未入库）。"""

    id: int | None
    content: str
    question_type: str = "scenario"
    difficulty: str = "mid"
    expected_points: list[str] = field(default_factory=list)
    rubric: dict = field(default_factory=dict)


REVIEW_REWRITE_PROMPT = """你是技术面试官。把给定题目改写成一个"换场景"的变体题：
- 保持同一能力项与同一考点，不要换成别的主题；
- 换一个项目场景或加一个约束，让候选人必须解释、不能靠背原题；
- 只输出 JSON：{"question": "改写后的一句话"}；只能有一个问号。"""


def _candidate_of(question: InterviewQuestion) -> ReviewCandidate:
    return ReviewCandidate(
        id=question.id,
        content=question.content,
        question_type=question.question_type or "concept",
        difficulty=question.difficulty or "mid",
        expected_points=[str(item) for item in (question.expected_points or [])],
        rubric=dict(question.rubric or {}),
    )


def _gap_terms(weak_point: WeakPoint) -> set[str]:
    return {item for item in tokenize(weak_point.gap_point or "") if len(item) >= 2}


def _gap_relevance(question: InterviewQuestion, terms: set[str]) -> int:
    """题目与缺口的词面重合度：只用来"筛掉明显不相关的题"，不做语义判断。"""
    if not terms:
        return 0
    # 只看题干与评分要点：能力项已经由 _related_questions 约束过，
    # 把它算进来会让"同能力项但考的是另一件事"蒙混过关
    text = " ".join(
        [
            question.content or "",
            " ".join(str(item) for item in (question.expected_points or [])),
        ]
    )
    overlap = terms & set(tokenize(text))
    # 只重合一个泛词（如"事务"）不算相关：要么重合两个词，要么命中一个长词
    if len(overlap) >= 2 or any(len(item) >= 4 for item in overlap):
        return len(overlap)
    return 0


def _recent_question_ids(db: Session, weak_point_id: int, limit: int = 5) -> set[int]:
    """最近用过的复查题：避免连续两次抽到同一道。"""
    rows = db.scalars(
        select(WeakPointPractice.question_id)
        .where(
            WeakPointPractice.weak_point_id == weak_point_id,
            WeakPointPractice.question_id.is_not(None),
        )
        .order_by(WeakPointPractice.id.desc())
        .limit(limit)
    ).all()
    return {int(item) for item in rows if item is not None}


def _rewrite_review_question(
    db: Session, weak_point: WeakPoint, difficulty: str
) -> ReviewCandidate | None:
    """题库没有可用变体题时，用原题改写一道（不落库，question_id 为空）。"""
    source_question = ""
    if weak_point.source_turn_id is not None:
        turn = db.get(InterviewTurn, weak_point.source_turn_id)
        source_question = (turn.question or "") if turn is not None else ""
    if not source_question:
        return None

    messages = [
        {"role": "system", "content": REVIEW_REWRITE_PROMPT},
        {
            "role": "user",
            "content": (
                f"<question>{source_question}</question>\n"
                f"<competency>{weak_point.topic}</competency>\n"
                f"<gap>{weak_point.gap_point or ''}</gap>"
            ),
        },
    ]
    for attempt in range(2):
        try:
            response = chat(messages, max_tokens=300, temperature=0.6)
            data = extract_json_object(response.content)
            text_value = str(data.get("question") or "").strip()
            if len(text_value) >= 8 and text_value.count("？") <= 1:
                return ReviewCandidate(
                    id=None,
                    content=text_value,
                    question_type="scenario",
                    difficulty=difficulty,
                    expected_points=[],
                    rubric={},
                )
        except (LLMError, ValueError, TypeError) as exc:
            logger.warning("复查题改写失败（第 %s 次）：%s", attempt + 1, exc)
    return None


def _pick_review_question(
    db: Session, weak_point: WeakPoint, question_id: int | None = None
) -> ReviewCandidate | None:
    """挑一道"变体题"做复查：同能力项、不是原题、最近没做过。

    优先级：显式指定 > 题库里未做过的（场景题优先、难度匹配阶段）
    > 题库里做过的 > 用原题改写一道。
    """
    if question_id is not None:
        question = db.get(InterviewQuestion, question_id)
        if question is None or question.status != "published":
            raise GrowthError("复查题目不存在或已下线", 404)
        return _candidate_of(question)

    target = _review_difficulty(weak_point.review_stage)
    source_id = _source_question_id(db, weak_point)
    candidates = [
        item
        for item in _related_questions(db, weak_point=weak_point, limit=10)
        if item.id != source_id
    ]

    terms = _gap_terms(weak_point)
    relevant = [item for item in candidates if _gap_relevance(item, terms) > 0]
    if not relevant:
        # 同能力项但没有一道题真的考到这条缺口：改写原题，而不是随便找一道
        return _rewrite_review_question(db, weak_point, target)

    recent = _recent_question_ids(db, weak_point.id)
    fresh = [item for item in relevant if item.id not in recent]
    pool = fresh or relevant
    pool.sort(
        key=lambda item: (
            item.question_type != "scenario",
            item.difficulty != target,
            -_gap_relevance(item, terms),
            item.id,
        )
    )
    return _candidate_of(pool[0])


SUGGESTION_SYSTEM_PROMPT = """你是技术面试辅导老师。候选人上一次回答漏掉了某条关键要点，
请给出 1-2 句"正确补法"，让他能直接照着讲出来。

规则：
1. 只能使用给定资料里的事实（原题、评分要点、题库补充），不要引入资料外的知识；
2. 先说"是什么/为什么"，再补"取舍或怎么验证"；
3. 不超过 120 字，不要写"你需要…"这种空话；
4. 只输出 JSON：{"suggestion": "补法"}"""


def _gap_suggestion(db: Session, weak_point: WeakPoint) -> str:
    """缺口卡上的"一句正确补法"：有资料时让模型写，失败回退模板。"""
    gap = (weak_point.gap_point or "").strip()
    fallback = (
        f"这条缺口是「{gap}」。补法：先用一句话说清它是什么、解决什么问题，"
        "再补一个具体场景或取舍理由，不要只背名词解释。"
        if gap
        else "这条缺口没有记录具体要点，先重看一遍面试反馈。"
    )

    materials: list[str] = []
    if weak_point.source_turn_id is not None:
        turn = db.get(InterviewTurn, weak_point.source_turn_id)
        if turn is not None:
            points = "；".join(
                str(item) for item in (turn.expected_points or []) if str(item).strip()
            )
            materials.append(
                f"<original_question>{turn.question}</original_question>\n"
                f"<expected_points>{points or '（无）'}</expected_points>\n"
                f"<candidate_answer>{(turn.answer or '')[:600]}</candidate_answer>"
            )
    for question in _related_questions(db, weak_point=weak_point, limit=3):
        points = "；".join(
            str(item) for item in (question.expected_points or []) if str(item).strip()
        )
        materials.append(
            f"<bank_question>{question.content}</bank_question>\n"
            f"<bank_points>{points or '（无）'}</bank_points>"
        )
    if not materials:
        return fallback

    messages = [
        {"role": "system", "content": SUGGESTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"<topic>{weak_point.topic}</topic>\n"
                f"<gap_point>{gap}</gap_point>\n"
                f"<gap_quote>{weak_point.gap_quote or '（无）'}</gap_quote>\n"
                + "\n".join(materials)
            ),
        },
    ]
    for attempt in range(2):
        try:
            response = chat(messages, max_tokens=400, temperature=0.4)
            data = extract_json_object(response.content)
            value = str(data.get("suggestion") or "").strip()
            if 10 <= len(value) <= 300:
                return value
        except (LLMError, ValueError, TypeError) as exc:
            logger.warning("缺口补法生成失败（第 %s 次）：%s", attempt + 1, exc)
    return fallback


def _fix_question(weak_point: WeakPoint, source_question: str = "") -> str:
    """修复阶段只要求补缺口，不要求重答整题；给出原题便于判卷对齐语境。"""
    prefix = f"原题是：{source_question}\n" if source_question else ""
    return (
        f"{prefix}不用重新回答整道题。你上次在「{weak_point.topic}」这块没讲清："
        f"{weak_point.gap_point}。用 1-3 句话把这一点补上，"
        "说清它是什么、为什么需要、或者怎么验证。"
    )


def _review_question_text(
    weak_point: WeakPoint, question: ReviewCandidate | None
) -> str:
    if question is not None:
        return question.content
    return (
        f"换个场景：如果项目里要用到「{weak_point.topic}」，"
        f"你会怎么讲清这一点——{weak_point.gap_point or '上次没讲透的地方'}？"
    )


def _review_points(
    weak_point: WeakPoint, question: ReviewCandidate | None
) -> tuple[list[str], dict]:
    """复查的判分要点：缺口固定放第一条（id=1），其余用题库要点。

    这样代码只需读 point_results 里 id=1 的状态，就能判断"这条缺口补没补上"，
    不需要再做任何语义匹配。
    """
    gap = (weak_point.gap_point or "").strip()
    points: list[str] = [gap] if gap else []
    rubric: dict = {}
    if question is not None:
        rubric = dict(question.rubric or {})
        for item in question.expected_points or []:
            text = str(item).strip()
            if text and text != gap:
                points.append(text)
    if not points:
        points = list(FREE_PRACTICE_POINTS)
    return points, rubric


def _log_action(
    db: Session,
    *,
    weak_point: WeakPoint,
    kind: str,
    question: str,
    answer: str,
    question_id: int | None,
    judgement: JudgementOut,
    gap_covered: bool | None,
    stage_before: int,
    stage_after: int,
) -> None:
    db.add(
        WeakPointPractice(
            user_id=weak_point.user_id,
            weak_point_id=weak_point.id,
            kind=kind,
            question_id=question_id,
            question=question,
            answer=answer,
            verdict=judgement.verdict,
            score=judgement.score,
            mastery_before=weak_point.mastery_score,
            mastery_after=weak_point.mastery_score,
            judgement=judgement.model_dump(),
            gap_covered=gap_covered,
            stage_before=stage_before,
            stage_after=stage_after,
        )
    )


def build_queue(db: Session, *, user_id: int) -> WeakPointQueueOut:
    """今日队列：待修复（open）+ 今日到期复查（fixed & next_review_at <= now）。"""
    now = datetime.now()
    points = list_weak_points(db, user_id=user_id, include_resolved=True)

    fix = [item for item in points if item.status == STATUS_OPEN and not item.resolved]
    review = [
        item
        for item in points
        if item.status == STATUS_FIXED
        and item.next_review_at is not None
        and item.next_review_at <= now
    ]
    future = [
        item.next_review_at
        for item in points
        if item.status == STATUS_FIXED
        and item.next_review_at is not None
        and item.next_review_at > now
    ]
    return WeakPointQueueOut(
        stats=QueueStatsOut(
            open=len(fix),
            due=len(review),
            resolved=len([item for item in points if item.resolved]),
        ),
        fix=[to_out(item) for item in fix],
        review=[to_out(item) for item in review],
        next_review_at=min(future) if future else None,
    )


def build_gap_card(db: Session, *, user_id: int, weak_point_id: int) -> GapCardOut:
    """缺口卡：原题 + 原话 + 缺的那一条 + 建议补法 + 复查题预览。"""
    weak_point = get_owned(db, user_id=user_id, weak_point_id=weak_point_id)

    source = GapSourceOut()
    if weak_point.source_turn_id is not None:
        turn = db.get(InterviewTurn, weak_point.source_turn_id)
        if turn is not None:
            source = GapSourceOut(
                session_id=turn.session_id,
                turn_id=turn.id,
                turn_index=turn.turn_index,
                question=turn.question,
                answer=turn.answer or "",
                quote=weak_point.gap_quote or "",
            )

    preview = _pick_review_question(db, weak_point)
    return GapCardOut(
        weak_point=to_out(weak_point),
        source=source,
        suggestion=_gap_suggestion(db, weak_point),
        review_question=(
            ReviewQuestionOut(
                question_id=preview.id,
                title=preview.content,
                type=_TYPE_LABEL.get(preview.question_type, "概念讲解"),
                difficulty=preview.difficulty or "mid",
                reason=f"同能力项变体题，难度 {preview.difficulty}",
            )
            if preview is not None
            else None
        ),
    )


def submit_fix(
    db: Session, *, user_id: int, weak_point_id: int, answer: str
) -> FixResultOut:
    """修复：只判"缺的那一条"，通过后进入 1 天后的复查。"""
    weak_point = get_owned(db, user_id=user_id, weak_point_id=weak_point_id)
    if weak_point.resolved or weak_point.status == STATUS_RESOLVED:
        raise GrowthError("这条已经掌握，不需要再修复", 409)
    if weak_point.status == STATUS_FIXED:
        raise GrowthError("这条已经修复，等待复查；到期后再来", 409)
    gap = (weak_point.gap_point or "").strip()
    if not gap:
        raise GrowthError("这条薄弱点没有记录具体缺口，请重新完成一场面试", 409)

    source_question = ""
    if weak_point.source_turn_id is not None:
        source_turn = db.get(InterviewTurn, weak_point.source_turn_id)
        source_question = (source_turn.question or "") if source_turn is not None else ""
    question = _fix_question(weak_point, source_question)
    try:
        judgement = judge_answer(
            question=question,
            expected_points=[gap],
            rubric={},
            answer=answer,
            position=weak_point.domain or "",
            depth=0,
        )
    except JudgeError as exc:
        raise GrowthError(str(exc), getattr(exc, "status_code", 502)) from exc

    row = next((item for item in judgement.point_results if item.get("id") == 1), {})
    gap_covered = row.get("status") == "covered"

    stage_before = weak_point.review_stage
    stage_after = stage_before
    if gap_covered:
        stage_after = 1
        weak_point.status = STATUS_FIXED
        weak_point.review_stage = stage_after
        weak_point.interval_days = FIRST_INTERVAL_DAYS
        weak_point.next_review_at = datetime.now() + timedelta(
            days=FIRST_INTERVAL_DAYS
        )
    weak_point.fix_count += 1

    _log_action(
        db,
        weak_point=weak_point,
        kind="fix",
        question=question,
        answer=answer,
        question_id=None,
        judgement=judgement,
        gap_covered=gap_covered,
        stage_before=stage_before,
        stage_after=stage_after,
    )
    db.commit()
    db.refresh(weak_point)

    return FixResultOut(
        judgement=judgement,
        gap_covered=gap_covered,
        weak_point=to_out(weak_point),
        before_answer=weak_point.gap_quote or "",
        after_answer=answer,
        message=(
            "补上了，1 天后会用一道变体题复查"
            if gap_covered
            else "还没补到这一点上，按建议重写一句再试"
        ),
    )


def submit_review(
    db: Session,
    *,
    user_id: int,
    weak_point_id: int,
    answer: str,
    question_id: int | None = None,
) -> ReviewResultOut:
    """复查：变体题 + 缺口作为第一条要点；通过则进入下一间隔。"""
    weak_point = get_owned(db, user_id=user_id, weak_point_id=weak_point_id)
    if weak_point.status != STATUS_FIXED or weak_point.resolved:
        raise GrowthError("这条还不在复查阶段，先完成修复", 409)

    question = _pick_review_question(db, weak_point, question_id)
    points, rubric = _review_points(weak_point, question)
    question_text = _review_question_text(weak_point, question)

    try:
        judgement = judge_answer(
            question=question_text,
            expected_points=points,
            rubric=rubric,
            answer=answer,
            position=weak_point.domain or "",
            depth=0,
        )
    except JudgeError as exc:
        raise GrowthError(str(exc), getattr(exc, "status_code", 502)) from exc

    row = next((item for item in judgement.point_results if item.get("id") == 1), {})
    gap_status = str(row.get("status") or "missing")
    gap_covered = gap_status == "covered"

    quality = _quality(gap_covered, gap_status, judgement.score)
    stage_before, stage_after = _apply_review_schedule(
        weak_point, quality=quality, now=datetime.now()
    )
    weak_point.review_count += 1
    weak_point.last_reviewed_at = datetime.now()

    _log_action(
        db,
        weak_point=weak_point,
        kind="review",
        question=question_text,
        answer=answer,
        question_id=question.id if question is not None else None,
        judgement=judgement,
        gap_covered=gap_covered,
        stage_before=stage_before,
        stage_after=stage_after,
    )
    db.commit()
    db.refresh(weak_point)

    if gap_covered:
        message = (
            "复查通过，这条已掌握"
            if weak_point.resolved
            else f"复查通过，{weak_point.interval_days} 天后再见"
        )
    else:
        message = "这条又忘了，已回到待修复；补好这一句后重新排期"

    return ReviewResultOut(
        question=question_text,
        judgement=judgement,
        gap_covered=gap_covered,
        weak_point=to_out(weak_point),
        message=message,
    )




def due_weak_points(
    db: Session, *, user_id: int, limit: int = 3
) -> list[WeakPoint]:
    """到期复查的缺口（面试建会话时注入简报用）。"""
    now = datetime.now()
    return list(
        db.scalars(
            select(WeakPoint)
            .where(
                WeakPoint.user_id == user_id,
                WeakPoint.status == STATUS_FIXED,
                WeakPoint.next_review_at.is_not(None),
                WeakPoint.next_review_at <= now,
            )
            .order_by(WeakPoint.next_review_at.asc(), WeakPoint.id)
            .limit(limit)
        ).all()
    )


def apply_interview_reviews(
    db: Session, session: InterviewSession, turns: list[InterviewTurn]
) -> int:
    """面试复查回写：本轮带了 review_weak_point_id 的，按缺口判定推进/重置。

    找不到缺口判定时跳过（例如面试官没把缺口放进 expected_points），
    不能因为元数据缺失把用户的复习进度清零。
    """
    now = datetime.now()
    changed = 0
    for turn in turns:
        if not turn.answer or not turn.review_weak_point_id:
            continue
        weak_point = db.get(WeakPoint, turn.review_weak_point_id)
        if weak_point is None or weak_point.user_id != session.user_id:
            continue
        gap = (weak_point.gap_point or "").strip()
        rows = (turn.judgement or {}).get("point_results") or []
        row = next(
            (item for item in rows if str(item.get("point") or "").strip() == gap),
            None,
        )
        if row is None:
            logger.info(
                "session %s turn %s 复查缺口未进入判分要点，跳过回写",
                session.id,
                turn.turn_index,
            )
            continue
        gap_status = str(row.get("status") or "missing")
        covered = gap_status == "covered"
        _apply_review_schedule(
            weak_point,
            quality=_quality(covered, gap_status, int(turn.score or 0)),
            now=now,
        )
        weak_point.review_count += 1
        weak_point.last_reviewed_at = now
        changed += 1
    return changed


__all__ = [
    "GrowthError",
    "apply_interview_reviews",
    "build_exercises",
    "build_gap_card",
    "build_queue",
    "build_stats",
    "due_weak_points",
    "get_owned",
    "list_weak_points",
    "resolve_weak_point",
    "submit_fix",
    "submit_practice",
    "submit_review",
    "sync_from_interview",
    "to_out",
]
