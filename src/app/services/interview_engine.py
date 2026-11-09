"""面试的"一步"业务：读轮次、去重、物化问题、落一轮、收尾评估。

这一层不关心谁调用它：老的顺序执行和图节点都走同样的函数，
保证两条路径的判卷、去重、覆盖统计行为一致。
"""

import difflib
import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InterviewQuestion, InterviewSession, InterviewTurn
from app.schemas.interview import InterviewEvaluationOut
from app.services.interview_context import resolve_domain, search_bank
from app.services.interview_director import choose_from_bank, write_evaluation

logger = logging.getLogger(__name__)

DUPLICATE_RATIO = 0.86
_VERDICT_SCORE = {"good": 88, "partial": 72, "bad": 45}
_COMPOUND_MARKERS = ("另外", "同时想", "以及", "顺便问", "还有就是")


def turns_of(db: Session, session_id: int) -> list[InterviewTurn]:
    """按轮次顺序读取一场面试的全部 turn。"""
    return list(
        db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == session_id)
            .order_by(InterviewTurn.turn_index, InterviewTurn.id)
        ).all()
    )


def pending_turn(turns: list[InterviewTurn]) -> InterviewTurn | None:
    """最后一条还没有回答的 turn，就是"当前题"。"""
    return next((turn for turn in reversed(turns) if not turn.answer), None)


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。？！、,.?!:：；;\"'“”‘’]", "", (text or "")).lower()


def too_similar(text: str, turns: list[InterviewTurn]) -> bool:
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


def is_compound(text: str) -> bool:
    """一次只问一个问题：出现两个问号或追加连词就判定为复合问题。"""
    if text.count("？") + text.count("?") > 1:
        return True
    return any(marker in text for marker in _COMPOUND_MARKERS)


def covered_competencies(session: InterviewSession) -> list[str]:
    coverage = session.coverage or {}
    return [str(item) for item in coverage.get("competencies") or []]


def record_coverage(session: InterviewSession, turn: InterviewTurn) -> None:
    """覆盖统计只记新话题；开场白与追问都不算新覆盖。"""
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


def pick_bank_question(
    db: Session, *, session: InterviewSession, decision, turns: list[InterviewTurn]
) -> dict:
    """题库检索 + 挑选改写；rubric 以数据库为准。"""
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
    return payload_from_bank_choice(db, decision=decision, choice=choice)


def payload_from_bank_choice(db: Session, *, decision, choice) -> dict:
    """把"选中哪道题"变成入库 payload；rubric 一律取数据库。"""
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


def materialize(
    db: Session, *, session: InterviewSession, decision, turns: list[InterviewTurn]
) -> dict:
    """把决策变成一条可直接入库的问题（含追问继承与来源标注）。"""
    last = turns[-1] if turns else None

    if decision.action == "followup":
        return {
            "question": (decision.question or "").strip(),
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
        return pick_bank_question(db, session=session, decision=decision, turns=turns)

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


def payload_problem(payload: dict, turns: list[InterviewTurn]) -> str | None:
    """返回不可入库的原因；None 表示通过。供"带提示重来一次"使用。"""
    if not payload.get("question"):
        return "上一个决策没有问题文本，请给出具体要问的一句话"
    if too_similar(payload["question"], turns):
        return "这个问题和已问过的题目重复，请换一个角度、能力项或更深一层"
    # 题库原题由人工维护，允许多个小问；现场生成的必须一次只问一个
    if (
        payload.get("source") != "bank"
        and payload.get("action") in {"ask", "followup"}
        and is_compound(payload["question"])
    ):
        return "一次只能问一个问题：把多个小问合成一个，只保留最关键的那一问"
    return None


def create_turn(
    db: Session,
    session: InterviewSession,
    *,
    turns: list[InterviewTurn],
    decision,
    payload: dict,
) -> InterviewTurn:
    """写入一轮问题并推进计数与覆盖统计。"""
    turn = InterviewTurn(
        session_id=session.id,
        turn_index=session.asked_count + 1,
        action=payload["action"],
        source=payload["source"],
        parent_turn_id=turns[-1].id if turns and payload["action"] == "followup" else None,
        depth=payload["depth"],
        competency=payload["competency"],
        question=payload["question"],
        rationale=(decision.reason or None) if decision is not None else None,
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
    record_coverage(session, turn)
    return turn


# --------------------------------------------------------------------------- #
# 收尾评估
# --------------------------------------------------------------------------- #
def _heuristic_narrative(turns: list[InterviewTurn], score: int) -> dict:
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


def build_evaluation(db: Session, session: InterviewSession) -> InterviewEvaluationOut:
    """总分由每轮得分求均值（可复算），文案由模型写（失败降级）。"""
    turns = turns_of(db, session.id)
    answered = [turn for turn in turns if turn.answer]

    scores = [
        turn.score if turn.score is not None else _VERDICT_SCORE.get(turn.verdict or "", 50)
        for turn in answered
    ]
    score = round(sum(scores) / len(scores)) if scores else 0
    score = max(0, min(100, score))

    covered = covered_competencies(session)
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


def close_session(db: Session, session: InterviewSession, *, reason: str) -> None:
    """生成评估并置为 finished；幂等（已有 evaluation 直接返回）。"""
    if session.evaluation:
        return
    evaluation = build_evaluation(db, session)
    session.status = "finished"
    session.finished_at = datetime.now()
    session.overall_score = evaluation.score
    session.summary = evaluation.description
    session.evaluation = evaluation.model_dump()
    logger.info("session %s 结束（%s），得分 %s", session.id, reason, evaluation.score)
