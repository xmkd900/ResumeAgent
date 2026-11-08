"""模拟面试编排。

流程（每一轮都从数据库重建状态，进程重启不丢上下文）：

    create:  背景快照 + 开场问题
    answer:  判卷 → 写回本轮 → 面试官决策 → 出下一题 / 收尾
    pause:   ongoing → paused（用户随时可以停）
    resume:  paused → ongoing
    finish:  汇总 → 结构化评估（幂等）

刻意不做的事：
- 不预生成题目列表（顺序和深度会变成常量，这就是"死板"的来源）；
- 不让模型直接改数据库状态（状态迁移由代码执行，模型只做决策）；
- 不在判卷失败时推进游标（整轮回滚，用户重试即可）。
"""

import difflib
import logging
import math
import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import InterviewQuestion, InterviewSession, InterviewTurn, Resume
from app.schemas.interview import (
    AnswerResponse,
    CurrentQuestionOut,
    InterviewEvaluationOut,
    InterviewSessionDetailOut,
    InterviewSessionOut,
    InterviewTurnOut,
)
from app.services.claim_extraction import ClaimExtractionError, extract_claims, sync_claims
from app.services.interview_context import (
    ContextError,
    competency_catalog,
    load_claims,
    load_owned_resume,
    load_weak_dimensions,
    resolve_domain,
    resume_excerpt,
    search_bank,
)
from app.services.interview_director import (
    DirectorError,
    build_briefing,
    choose_from_bank,
    decide,
    write_evaluation,
)
from app.services.interview_judge import JudgeError, judge_answer

logger = logging.getLogger(__name__)

DEFAULT_MAX_QUESTIONS = 12
MIN_QUESTIONS = 4
DUPLICATE_RATIO = 0.86

_VERDICT_SCORE = {"good": 88, "partial": 72, "bad": 45}


class InterviewError(Exception):
    """面试服务异常。
    
    Attributes:
        status_code: HTTP状态码，默认409
    """
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class SessionNotFound(InterviewError):
    """面试会话不存在异常。
    
    Attributes:
        message: 错误信息
    """
    def __init__(self, message: str = "面试会话不存在"):
        super().__init__(message, 404)


class InvalidSessionState(InterviewError):
    """面试会话状态异常。"""
    pass


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def _get_owned_session(
    db: Session, *, user_id: int, session_id: int, for_update: bool = False
) -> InterviewSession:
    """获取用户拥有的面试会话，带权限校验。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        session_id: 会话ID
        for_update: 是否加锁（用于更新操作）
    
    Returns:
        面试会话对象
    
    Raises:
        SessionNotFound: 会话不存在或无权限
    """
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


def _turns(db: Session, session_id: int) -> list[InterviewTurn]:
    """获取会话的所有回合，按轮次排序。
    
    Args:
        db: 数据库会话
        session_id: 会话ID
    
    Returns:
        回合列表
    """
    return list(
        db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == session_id)
            .order_by(InterviewTurn.turn_index, InterviewTurn.id)
        ).all()
    )


def _normalize(text: str) -> str:
    """文本规范化：去除标点和空白，转小写。
    
    Args:
        text: 原始文本
    
    Returns:
        规范化后的文本
    """
    return re.sub(r"[\s，。？！、,.?!:：；;\"'“”‘’]", "", (text or "")).lower()


def _too_similar(text: str, turns: list[InterviewTurn]) -> bool:
    """检查问题是否与已问过的问题过于相似。
    
    Args:
        text: 待检查的问题
        turns: 已有的回合列表
    
    Returns:
        是否过于相似
    """
    candidate = _normalize(text)
    if not candidate:
        return True
    for turn in turns:
        existing = _normalize(turn.question)
        if not existing:
            continue
        if candidate == existing:
            return True
        if difflib.SequenceMatcher(None, candidate, existing).ratio() >= DUPLICATE_RATIO:
            return True
    return False


_COMPOUND_MARKERS = ("另外", "同时想", "以及", "顺便问", "还有就是")


def _is_compound(text: str) -> bool:
    """检查是否是复合问题（一次问多个小问）。
    
    Args:
        text: 问题文本
    
    Returns:
        是否是复合问题
    """
    if text.count("？") + text.count("?") > 1:
        return True
    return any(marker in text for marker in _COMPOUND_MARKERS)


def _current_question(turns: list[InterviewTurn]) -> CurrentQuestionOut | None:
    """获取当前待回答的问题。
    
    Args:
        turns: 回合列表
    
    Returns:
        当前问题对象，如果没有待答问题则返回None
    """
    pending = next((turn for turn in reversed(turns) if not turn.answer), None)
    if pending is None:
        return None
    return CurrentQuestionOut(
        turn_id=pending.id,
        turn_index=pending.turn_index,
        depth=pending.depth,
        content=pending.question,
        competency=pending.competency or "综合",
        source=pending.source,  # type: ignore[arg-type]
        action=pending.action,  # type: ignore[arg-type]
    )


def _covered(session: InterviewSession) -> list[str]:
    """获取已覆盖的能力维度列表。
    
    Args:
        session: 面试会话
    
    Returns:
        已覆盖的能力维度列表
    """
    coverage = session.coverage or {}
    return [str(item) for item in coverage.get("competencies") or []]


def _detail(db: Session, session: InterviewSession) -> InterviewSessionDetailOut:
    """构建会话详情。
    
    Args:
        db: 数据库会话
        session: 面试会话
    
    Returns:
        会话详情对象
    """
    turns = _turns(db, session.id)
    base = InterviewSessionOut.model_validate(session)
    evaluation = (
        InterviewEvaluationOut.model_validate(session.evaluation)
        if session.evaluation
        else None
    )
    current = _current_question(turns) if session.status == "ongoing" else None
    warnings: list[str] = []
    if (session.briefing or {}).get("claims_source") == "failed":
        warnings.append(
            "简历要点抽取失败，本场按 JD 与题库出题；可到简历页点「提取面试要点」后重新开始"
        )
    return InterviewSessionDetailOut(
        **base.model_dump(),
        turns=[InterviewTurnOut.model_validate(turn) for turn in turns],
        current_question=current,
        evaluation=evaluation,
        covered_competencies=_covered(session),
        remaining_questions=max(0, session.max_questions - session.asked_count),
        warnings=warnings,
    )


def get_interview_detail(
    db: Session, *, user_id: int, session_id: int
) -> InterviewSessionDetailOut:
    """获取面试会话详情。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        session_id: 会话ID
    
    Returns:
        会话详情对象
    """
    session = _get_owned_session(db, user_id=user_id, session_id=session_id)
    return _detail(db, session)


# --------------------------------------------------------------------------- #
# 建会话
# --------------------------------------------------------------------------- #
def _ensure_claims(
    db: Session, resume: Resume, claims: list
) -> tuple[list, str]:
    """保证建会话时简历要点可用：没有就补抽一次。

    抽取失败不阻塞面试：降级为 JD/题库出题，并在 briefing 里记录来源，
    复盘时能看出"这场为什么没问项目"。
    
    Args:
        db: 数据库会话
        resume: 简历对象
        claims: 已有的简历声明列表
    
    Returns:
        (简历声明列表, 来源标识)
        来源标识：existing/extracted/failed/none
    """
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
    """创建面试会话并生成开场问题；失败不留半成品。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        position: 岗位名称
        resume_id: 简历ID（可选）
        jd_text: JD文本（可选）
        max_questions: 最大题数（可选）
    
    Returns:
        会话详情对象
    
    Raises:
        InterviewError: 创建失败
    """
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
    # 记录要点来源：existing 已有 / extracted 本次补抽 / failed 抽取失败降级 / none 无简历
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
    _record_coverage(session, turn)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(session)
    return _detail(db, session)


# --------------------------------------------------------------------------- #
# 出下一题
# --------------------------------------------------------------------------- #
def _record_coverage(session: InterviewSession, turn: InterviewTurn) -> None:
    """更新覆盖统计：只记录新话题（ask动作），开场和追问不算。
    
    Args:
        session: 面试会话
        turn: 当前回合
    """
    coverage = dict(session.coverage or {})
    competencies = list(coverage.get("competencies") or [])
    claim_ids = list(coverage.get("claim_ids") or [])

    if turn.action == "ask" and turn.competency and turn.competency not in competencies:
        competencies.append(turn.competency)
    if turn.claim_id is not None and turn.claim_id not in claim_ids:
        claim_ids.append(turn.claim_id)

    coverage["competencies"] = competencies
    coverage["claim_ids"] = claim_ids
    session.coverage = coverage


def _pick_bank_question(
    db: Session, *, session: InterviewSession, decision, turns: list[InterviewTurn]
):
    """从题库选择并具体化问题。
    
    Args:
        db: 数据库会话
        session: 面试会话
        decision: 面试官决策
        turns: 回合列表
    
    Returns:
        具体化的问题字典
    """
    used_ids = {turn.question_id for turn in turns if turn.question_id is not None}
    domain = (session.briefing or {}).get("domain") or resolve_domain(session.position)
    candidates = search_bank(
        db,
        domain=domain,
        query=decision.search_query or decision.competency or "",
        competency=decision.search_competency or decision.competency or None,
        difficulty=decision.search_difficulty,
        exclude_ids=used_ids,
        limit=5,
    )
    choice = choose_from_bank(
        briefing=session.briefing or {},
        turns=turns,
        decision=decision,
        candidates=candidates,
    )

    question: InterviewQuestion | None = None
    if choice.question_id is not None:
        question = db.get(InterviewQuestion, choice.question_id)

    expected = choice.expected_points
    rubric: dict = {}
    competency = choice.competency or decision.competency or ""
    if question is not None:
        expected = list(question.expected_points or []) or expected
        rubric = dict(question.rubric or {})
        competency = question.competency or competency

    return {
        "question": choice.question.strip(),
        "competency": competency or "综合",
        "expected_points": expected[:6],
        "rubric": rubric,
        "question_id": question.id if question is not None else None,
        "claim_id": None,
        "source": "bank",
        "action": "ask",
        "depth": 0,
    }


def _materialize(
    db: Session, *, session: InterviewSession, decision, turns: list[InterviewTurn]
) -> dict:
    """根据面试官决策具体化问题。
    
    Args:
        db: 数据库会话
        session: 面试会话
        decision: 面试官决策
        turns: 回合列表
    
    Returns:
        具体化的问题字典，包含：
        - question: 问题文本
        - competency: 能力维度
        - expected_points: 期望得分点
        - rubric: 评分标准
        - question_id: 题库题目ID
        - claim_id: 简历声明ID
        - source: 问题来源
        - action: 动作类型
        - depth: 深度
    """
    last = turns[-1] if turns else None

    if decision.action == "followup":
        question = (decision.question or "").strip()
        return {
            "question": question,
            "competency": decision.competency or (last.competency if last else "综合"),
            "expected_points": decision.expected_points
            or (list(last.expected_points or []) if last else []),
            "rubric": dict(last.rubric or {}) if last else {},
            "question_id": last.question_id if last else None,
            "claim_id": last.claim_id if last else None,
            "source": last.source if last else "generated",
            "action": "followup",
            "depth": (last.depth if last else 0) + 1,
        }

    if decision.action == "search_bank":
        return _pick_bank_question(db, session=session, decision=decision, turns=turns)

    anchor = (decision.anchor or "general").lower()
    source = {"resume": "resume", "jd": "jd", "bank": "bank"}.get(anchor, "generated")
    return {
        "question": (decision.question or "").strip(),
        "competency": decision.competency or "综合",
        "expected_points": decision.expected_points or [],
        "rubric": {},
        "question_id": None,
        "claim_id": decision.claim_id if source == "resume" else None,
        "source": source,
        "action": "ask",
        "depth": 0,
    }


def _advance(db: Session, session: InterviewSession) -> InterviewTurn | None:
    """让面试官决定下一题；返回 None 表示本场结束。
    
    Args:
        db: 数据库会话
        session: 面试会话
    
    Returns:
        下一回合对象，如果结束则返回None
    
    Raises:
        DirectorError: 决策失败
    """
    if session.asked_count >= session.max_questions:
        logger.info("session %s 达到题目预算 %s，收尾", session.id, session.max_questions)
        return None

    turns = _turns(db, session.id)
    note: str | None = None

    for attempt in range(2):
        decision = decide(
            briefing=session.briefing or {},
            turns=turns,
            asked_count=session.asked_count,
            min_questions=session.min_questions,
            max_questions=session.max_questions,
            note=note,
        )
        if decision.action == "finish":
            logger.info("面试官决定收尾：%s", decision.reason)
            return None

        payload = _materialize(db, session=session, decision=decision, turns=turns)
        if not payload["question"]:
            note = "上一个决策没有问题文本，请给出具体要问的一句话"
            continue
        if _too_similar(payload["question"], turns) and attempt == 0:
            note = "这个问题和已问过的题目重复，请换一个角度、能力项或更深一层"
            logger.info("命中重复题目，重新决策")
            continue
        # 题库原题由人工维护，允许多个小问；现场生成的必须一次只问一个
        if (
            payload["source"] != "bank"
            and payload["action"] in {"ask", "followup"}
            and _is_compound(payload["question"])
            and attempt == 0
        ):
            note = "一次只能问一个问题：把多个小问合成一个，只保留最关键的那一问"
            logger.info("命中复合问题，重新决策")
            continue

        turn = InterviewTurn(
            session_id=session.id,
            turn_index=session.asked_count + 1,
            action=payload["action"],
            source=payload["source"],
            parent_turn_id=turns[-1].id if turns and payload["action"] == "followup" else None,
            depth=payload["depth"],
            competency=payload["competency"],
            question=payload["question"],
            rationale=decision.reason or None,
            expected_points=payload["expected_points"],
            rubric=payload["rubric"],
            question_id=payload["question_id"],
            claim_id=payload["claim_id"],
        )
        db.add(turn)
        db.flush()

        session.asked_count += 1
        if turn.action == "followup":
            session.asked_followups += 1
        _record_coverage(session, turn)
        return turn

    raise DirectorError("面试官连续两次没有给出可用的新问题")


# --------------------------------------------------------------------------- #
# 提交回答
# --------------------------------------------------------------------------- #
def submit_answer(
    db: Session, *, user_id: int, session_id: int, answer: str
) -> AnswerResponse:
    """提交回答：判卷 + 推进；任一步失败整轮回滚，不留下半截状态。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        session_id: 会话ID
        answer: 回答文本
    
    Returns:
        回答响应，包含判卷结果和下一题
    
    Raises:
        InvalidSessionState: 会话状态异常
        JudgeError: 判卷失败
        DirectorError: 决策失败
    """
    session = _get_owned_session(db, user_id=user_id, session_id=session_id, for_update=True)

    if session.status == "paused":
        raise InvalidSessionState("面试已暂停，请先继续面试")
    if session.status != "ongoing":
        raise InvalidSessionState("面试已结束")
    if not session.briefing:
        raise InvalidSessionState("该会话由旧版本创建，请重新开始一场面试")

    turns = _turns(db, session.id)
    pending = next((turn for turn in reversed(turns) if not turn.answer), None)
    if pending is None:
        raise InvalidSessionState("当前没有待回答的问题")

    try:
        judgement = judge_answer(
            question=pending.question,
            expected_points=list(pending.expected_points or []),
            rubric=dict(pending.rubric or {}),
            answer=answer,
        )
    except JudgeError:
        db.rollback()
        raise

    pending.answer = answer
    pending.judgement = judgement.model_dump()
    pending.verdict = judgement.verdict
    pending.score = judgement.score
    pending.answered_at = datetime.now()
    db.flush()

    try:
        next_turn = _advance(db, session)
    except Exception:
        # 判卷结果也一起回滚：用户重试同一条回答即可，不产生"答了但没下一题"的僵局
        db.rollback()
        raise

    finished = next_turn is None
    if finished:
        _close(db, session, reason="director")

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(session)

    return AnswerResponse(
        judgement=judgement,
        next_question=(
            CurrentQuestionOut(
                turn_id=next_turn.id,
                turn_index=next_turn.turn_index,
                depth=next_turn.depth,
                content=next_turn.question,
                competency=next_turn.competency or "综合",
                source=next_turn.source,  # type: ignore[arg-type]
                action=next_turn.action,  # type: ignore[arg-type]
            )
            if next_turn is not None
            else None
        ),
        finished=finished,
        asked_count=session.asked_count,
        max_questions=session.max_questions,
    )


# --------------------------------------------------------------------------- #
# 收尾与评估
# --------------------------------------------------------------------------- #
def _heuristic_narrative(turns: list[InterviewTurn], score: int) -> dict:
    """使用规则生成评估文案（LLM失败时的兜底方案）。
    
    Args:
        turns: 回合列表
        score: 总分
    
    Returns:
        评估文案字典
    """
    answered = [turn for turn in turns if turn.answer]
    solved = [turn for turn in answered if turn.verdict == "good"]
    weak = [turn for turn in answered if turn.verdict == "bad"]

    strengths: list[str] = [
        f"{turn.competency or '综合'}：能覆盖关键要点并给出依据" for turn in solved[:3]
    ]
    if not strengths and answered:
        strengths.append("能围绕问题给出方向性回答，具备继续深挖的基础")

    improvements: list[str] = [
        f"{turn.competency or '综合'} 的关键结论还没讲透，下一场先给因果再给结论"
        for turn in weak[:2]
    ]
    if not improvements and answered:
        improvements.append("回答里补上验证方式：指标怎么测、怎么证明是你的改动带来的")

    headline = (
        "技术判断扎实，能把结论说清楚。"
        if score >= 80
        else "方向基本正确，细节和验证还需要补。"
        if score >= 60
        else "基础还需要补，先把核心概念讲准确。"
    )
    return {
        "headline": headline,
        "description": (
            f"本场共 {len(turns)} 轮、回答 {len(answered)} 轮，"
            f"其中 {len(solved)} 轮要点齐全、{len(weak)} 轮需要补强。"
        ),
        "strengths": strengths[:4],
        "improvements": improvements[:4],
    }


def _build_evaluation(db: Session, session: InterviewSession) -> InterviewEvaluationOut:
    """构建面试评估报告。
    
    Args:
        db: 数据库会话
        session: 面试会话
    
    Returns:
        评估报告对象
    """
    turns = _turns(db, session.id)
    answered = [turn for turn in turns if turn.answer]

    scores = [
        turn.score if turn.score is not None else _VERDICT_SCORE.get(turn.verdict or "", 50)
        for turn in answered
    ]
    score = round(sum(scores) / len(scores)) if scores else 0
    score = max(0, min(100, score))

    covered = _covered(session)
    hits = 0
    total_points = 0
    for turn in answered:
        total_points += len(turn.expected_points or [])
        if isinstance(turn.judgement, dict):
            hits += len(turn.judgement.get("hit_points") or [])

    try:
        narrative = write_evaluation(
            position=session.position,
            turns=turns,
            score=score,
            covered=covered,
        )
        data = narrative.model_dump()
    except Exception as exc:  # noqa: BLE001  评估文案失败不能把用户卡在面试里
        logger.warning("评估文案生成失败，改用规则摘要：%s", exc)
        data = _heuristic_narrative(turns, score)

    return InterviewEvaluationOut(
        score=score,
        headline=data.get("headline") or "本场面试已完成",
        description=data.get("description") or "",
        stats=[
            {"label": "回答轮次", "value": str(len(answered)), "suffix": "轮"},
            {"label": "覆盖能力", "value": str(len(covered)), "suffix": "项"},
            {
                "label": "要点覆盖",
                "value": f"{hits}/{total_points}" if total_points else "—",
                "suffix": "",
            },
            {"label": "追问", "value": str(session.asked_followups), "suffix": "次"},
        ],
        strengths=data.get("strengths") or [],
        improvements=data.get("improvements") or [],
    )


def _close(db: Session, session: InterviewSession, *, reason: str) -> None:
    """结束面试：生成评估并落库；幂等（已有 evaluation 直接返回）。
    
    Args:
        db: 数据库会话
        session: 面试会话
        reason: 结束原因
    """
    if session.evaluation:
        return
    evaluation = _build_evaluation(db, session)
    session.status = "finished"
    session.finished_at = datetime.now()
    session.overall_score = evaluation.score
    session.summary = evaluation.description
    session.evaluation = evaluation.model_dump()
    logger.info("session %s 结束（%s），得分 %s", session.id, reason, evaluation.score)


def finish_interview(
    db: Session, *, user_id: int, session_id: int
) -> InterviewSessionDetailOut:
    """用户主动结束面试并生成评估。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        session_id: 会话ID
    
    Returns:
        会话详情对象
    
    Raises:
        InvalidSessionState: 会话状态异常
    """
    session = _get_owned_session(db, user_id=user_id, session_id=session_id, for_update=True)
    if session.status == "aborted":
        raise InvalidSessionState("面试已中止，不能生成评估")
    if not session.evaluation:
        _close(db, session, reason="user")
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
    """用户主动暂停：保留当前待答问题，回来可以接着答。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        session_id: 会话ID
    
    Returns:
        会话详情对象
    
    Raises:
        InvalidSessionState: 会话状态异常
    """
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
    """用户继续暂停的面试。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        session_id: 会话ID
    
    Returns:
        会话详情对象
    
    Raises:
        InvalidSessionState: 会话状态异常
    """
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
    """中止面试。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        session_id: 会话ID
    
    Returns:
        会话详情对象
    """
    session = _get_owned_session(db, user_id=user_id, session_id=session_id, for_update=True)
    if session.status == "ongoing":
        session.status = "aborted"
        db.commit()
        db.refresh(session)
    return _detail(db, session)


def list_interviews(
    db: Session, *, user_id: int, page: int = 1, page_size: int = 20
) -> tuple[list[InterviewSession], int]:
    """分页获取用户的面试会话列表。
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        page: 页码
        page_size: 每页数量
    
    Returns:
        (会话列表, 总数)
    """
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


def summarize_progress(session: InterviewSession) -> dict:
    """生成进度快照（用于日志/调试）。
    
    Args:
        session: 面试会话
    
    Returns:
        进度字典
    """
    return {
        "asked": session.asked_count,
        "max": session.max_questions,
        "ratio": round(session.asked_count / max(1, session.max_questions), 2),
        "followups": session.asked_followups,
        "covered": len(_covered(session)),
    }


def estimated_remaining(session: InterviewSession) -> int:
    """估算剩余题数。
    
    Args:
        session: 面试会话
    
    Returns:
        剩余题数
    """
    return math.ceil(max(0, session.max_questions - session.asked_count))


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
