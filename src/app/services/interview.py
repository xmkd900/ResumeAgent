"""模拟面试服务层：会话生命周期与事务边界。

单轮编排交给 `interview_graph`（LangGraph 状态图）：
    create  → 建会话并让图停在"等待回答"
    answer  → Command(resume) 恢复图：判卷 → 决策 → 出下一题 / 收尾
    pause   → 只改业务状态，图仍停在 interrupt 处
    finish  → 用户主动收尾，生成评估

这里只负责权限、状态校验、事务提交/回滚与 DTO 组装。
"""

import logging
from collections.abc import Iterator

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import InterviewSession, InterviewTurn, Resume
from app.schemas.interview import (
    AnswerResponse,
    InterviewEvaluationOut,
    InterviewSessionDetailOut,
    InterviewSessionOut,
    InterviewTurnOut,
    JudgementOut,
)
from app.services import growth
from app.services import interview_engine as engine
from app.services.claim_extraction import ClaimExtractionError, extract_claims, sync_claims
from app.services.interview_context import (
    ContextError,
    competency_catalog,
    load_claims,
    load_owned_resume,
    load_weak_dimensions,
    resolve_domain,
    resume_excerpt,
)
from app.services.interview_director import build_briefing
from app.services.interview_graph import (
    resume_with_answer,
    start_session,
    stream_answer_events,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_QUESTIONS = 12
MIN_QUESTIONS = 4


class InterviewError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class SessionNotFound(InterviewError):
    def __init__(self, message: str = "面试会话不存在"):
        super().__init__(message, 404)


class InvalidSessionState(InterviewError):
    pass


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def _get_owned_session(
    db: Session, *, user_id: int, session_id: int, for_update: bool = False
) -> InterviewSession:
    statement = select(InterviewSession).where(
        InterviewSession.id == session_id,
        InterviewSession.user_id == user_id,
    )
    if for_update:
        statement = statement.with_for_update()
    session = db.scalar(statement)
    if session is None:
        raise SessionNotFound()
    return session


def _current_question(turns: list[InterviewTurn]):
    pending = engine.pending_turn(turns)
    if pending is None:
        return None
    from app.schemas.interview import CurrentQuestionOut

    return CurrentQuestionOut(
        turn_id=pending.id,
        turn_index=pending.turn_index,
        depth=pending.depth,
        content=pending.question,
        competency=pending.competency or "综合",
        source=pending.source,  # type: ignore[arg-type]
        action=pending.action,  # type: ignore[arg-type]
    )


def _detail(db: Session, session: InterviewSession) -> InterviewSessionDetailOut:
    turns = engine.turns_of(db, session.id)
    base = InterviewSessionOut.model_validate(session)
    evaluation = (
        InterviewEvaluationOut.model_validate(session.evaluation)
        if session.evaluation
        else None
    )
    warnings: list[str] = []
    if (session.briefing or {}).get("claims_source") == "failed":
        warnings.append(
            "简历要点抽取失败，本场按 JD 与题库出题；可到简历页点「提取面试要点」后重新开始"
        )
    return InterviewSessionDetailOut(
        **base.model_dump(),
        turns=[InterviewTurnOut.model_validate(turn) for turn in turns],
        current_question=_current_question(turns) if session.status == "ongoing" else None,
        evaluation=evaluation,
        covered_competencies=engine.covered_competencies(session),
        remaining_questions=max(0, session.max_questions - session.asked_count),
        warnings=warnings,
    )


def get_interview_detail(
    db: Session, *, user_id: int, session_id: int
) -> InterviewSessionDetailOut:
    session = _get_owned_session(db, user_id=user_id, session_id=session_id)
    return _detail(db, session)


# --------------------------------------------------------------------------- #
# 建会话
# --------------------------------------------------------------------------- #
def _ensure_claims(db: Session, resume: Resume, claims: list) -> tuple[list, str]:
    """没有简历要点就补抽一次；失败降级，不阻塞面试。"""
    if claims:
        return claims, "existing"

    raw_text = (resume.raw_text or "").strip()
    if not raw_text:
        return [], "none"

    try:
        drafts = extract_claims(raw_text)
        if not drafts:
            return [], "empty"
        rows = sync_claims(db, resume.id, drafts)
        logger.info("简历 %s 补抽面试要点 %s 条", resume.id, len(rows))
        return rows, "extracted"
    except ClaimExtractionError as exc:
        logger.warning("简历要点抽取失败，降级为 JD/题库出题：%s", exc)
        return [], "failed"
    except Exception:  # 抽取异常不能阻塞面试创建
        logger.exception("简历要点抽取异常，降级为 JD/题库出题")
        return [], "failed"


def create_interview(
    db: Session,
    *,
    user_id: int,
    position: str,
    resume_id: int | None,
    jd_text: str | None,
    max_questions: int | None = None,
) -> InterviewSessionDetailOut:
    """建会话：冻结背景快照 + 开场问题，然后让图停在等待回答。"""
    cleaned_jd = (jd_text or "").strip() or None
    budget = max_questions or DEFAULT_MAX_QUESTIONS
    min_questions = min(MIN_QUESTIONS, max(1, budget - 1))

    resume: Resume | None = None
    claims: list = []
    claims_source = "none"
    if resume_id is not None:
        resume = load_owned_resume(db, resume_id, user_id)
        if resume.parse_status != "done" or not resume.raw_text:
            raise InterviewError("简历尚未解析完成", 409)
        claims, claims_source = _ensure_claims(db, resume, load_claims(db, resume.id))

    domain = resolve_domain(position)
    catalog = competency_catalog(db, domain)
    if not catalog and not claims:
        raise InterviewError("题库为空且简历没有可用要点，无法开始面试", 409)

    weak_dimensions = load_weak_dimensions(db, resume.id) if resume else []
    briefing, opening = build_briefing(
        position=position,
        jd_text=cleaned_jd,
        resume_text=resume_excerpt(resume),
        claims=claims,
        catalog=catalog,
        domain=domain,
    )
    if weak_dimensions:
        briefing["weak_dimensions"] = weak_dimensions

    # 成长闭环：把"已修复且到期"的缺口带进这场面试，让面试官用变体题复查
    due_points = growth.due_weak_points(db, user_id=user_id, limit=3)
    if due_points:
        briefing["due_weak_points"] = [
            {
                "weak_point_id": point.id,
                "topic": point.topic,
                "gap_point": point.gap_point,
                "stage": point.review_stage,
            }
            for point in due_points
        ]
    # existing 已有 / extracted 本次补抽 / failed 抽取失败降级 / none 无简历
    briefing["claims_source"] = claims_source

    session = InterviewSession(
        user_id=user_id,
        resume_id=resume_id,
        position=position,
        jd_text=cleaned_jd,
        status="ongoing",
        max_questions=budget,
        min_questions=min_questions,
        asked_count=1,
        briefing=briefing,
        coverage={"competencies": [], "claim_ids": []},
    )
    db.add(session)
    db.flush()

    turn = InterviewTurn(
        session_id=session.id,
        turn_index=1,
        action="open",
        source="resume" if claims else "generated",
        depth=0,
        competency=opening.competency or "自我介绍",
        question=opening.question.strip(),
        rationale="开场：让候选人先讲清背景",
        expected_points=opening.expected_points or [],
        rubric={},
    )
    db.add(turn)
    engine.record_coverage(session, turn)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(session)

    # 初始化图：走到 await 处停住，建立 checkpoint；失败只降级，不影响会话
    try:
        start_session(db, session.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("图初始化失败，首次回答将走快速路径：%s", exc)

    return _detail(db, session)


# --------------------------------------------------------------------------- #
# 提交回答
# --------------------------------------------------------------------------- #
def prepare_answer(db: Session, *, user_id: int, session_id: int) -> InterviewSession:
    """提交回答前的校验与行锁；这类错误在开始流式响应之前就要抛出。"""
    session = _get_owned_session(db, user_id=user_id, session_id=session_id, for_update=True)
    if session.status == "paused":
        raise InvalidSessionState("面试已暂停，请先继续面试")
    if session.status != "ongoing":
        raise InvalidSessionState("面试已结束")
    if not session.briefing:
        raise InvalidSessionState("该会话由旧版本创建，请重新开始一场面试")
    if engine.pending_turn(engine.turns_of(db, session.id)) is None:
        raise InvalidSessionState("当前没有待回答的问题")
    return session


def _answer_response(db: Session, session: InterviewSession) -> AnswerResponse:
    turns = engine.turns_of(db, session.id)
    answered = next((turn for turn in reversed(turns) if turn.answer), None)
    if answered is None or not answered.judgement:
        raise InterviewError("本轮回答未产生判卷结果，请重试", 502)
    return AnswerResponse(
        judgement=JudgementOut.model_validate(answered.judgement),
        next_question=_current_question(turns),
        finished=session.status == "finished",
        asked_count=session.asked_count,
        max_questions=session.max_questions,
    )


def submit_answer(
    db: Session, *, user_id: int, session_id: int, answer: str
) -> AnswerResponse:
    """一次性返回结果（脚本/兼容用）；交互界面走 stream_answer。"""
    session = prepare_answer(db, user_id=user_id, session_id=session_id)
    try:
        resume_with_answer(db, session.id, answer)
        response = _answer_response(db, session)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return response


def stream_answer(
    db: Session, session: InterviewSession, answer: str
) -> Iterator[dict]:
    """逐节点产出事件：stage（进度）/ result（最终结果）/ error（失败）。

    事务在流结束时才提交；中间阶段只代表"做到哪一步"，不代表已落库。
    """
    try:
        for mode, chunk in stream_answer_events(db, session.id, answer):
            if mode == "custom":
                yield {"event": "stage", "data": chunk}
        response = _answer_response(db, session)
        db.commit()
        yield {"event": "result", "data": response.model_dump(mode="json")}
    except Exception as exc:
        db.rollback()
        logger.exception("流式回答失败")
        yield {
            "event": "error",
            "data": {
                "detail": str(exc) or "面试服务暂时不可用，请稍后重试",
                "status": getattr(exc, "status_code", 502),
            },
        }


# --------------------------------------------------------------------------- #
# 状态流转
# --------------------------------------------------------------------------- #
def finish_interview(
    db: Session, *, user_id: int, session_id: int
) -> InterviewSessionDetailOut:
    session = _get_owned_session(db, user_id=user_id, session_id=session_id, for_update=True)
    if session.status == "aborted":
        raise InvalidSessionState("面试已中止，不能生成评估")
    if not session.evaluation:
        engine.close_session(db, session, reason="user")
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    db.refresh(session)
    return _detail(db, session)


def pause_interview(
    db: Session, *, user_id: int, session_id: int
) -> InterviewSessionDetailOut:
    session = _get_owned_session(db, user_id=user_id, session_id=session_id, for_update=True)
    if session.status == "finished":
        raise InvalidSessionState("面试已结束")
    if session.status == "aborted":
        raise InvalidSessionState("面试已中止")
    if session.status == "ongoing":
        session.status = "paused"
        db.commit()
        db.refresh(session)
    return _detail(db, session)


def resume_interview(
    db: Session, *, user_id: int, session_id: int
) -> InterviewSessionDetailOut:
    session = _get_owned_session(db, user_id=user_id, session_id=session_id, for_update=True)
    if session.status in {"finished", "aborted"}:
        raise InvalidSessionState("面试已结束，不能继续")
    if session.status == "paused":
        session.status = "ongoing"
        db.commit()
        db.refresh(session)
    return _detail(db, session)


def abort_interview(
    db: Session, *, user_id: int, session_id: int
) -> InterviewSessionDetailOut:
    session = _get_owned_session(db, user_id=user_id, session_id=session_id, for_update=True)
    if session.status == "ongoing":
        session.status = "aborted"
        db.commit()
        db.refresh(session)
    return _detail(db, session)


def list_interviews(
    db: Session, *, user_id: int, page: int = 1, page_size: int = 20
) -> tuple[list[InterviewSession], int]:
    total = db.scalar(
        select(func.count()).select_from(InterviewSession).where(
            InterviewSession.user_id == user_id
        )
    ) or 0
    rows = list(
        db.scalars(
            select(InterviewSession)
            .where(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.started_at.desc(), InterviewSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, int(total)


__all__ = [
    "ContextError",
    "InterviewError",
    "InvalidSessionState",
    "SessionNotFound",
    "abort_interview",
    "create_interview",
    "finish_interview",
    "get_interview_detail",
    "list_interviews",
    "pause_interview",
    "resume_interview",
    "submit_answer",
]
