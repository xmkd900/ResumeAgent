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

from app.models import InterviewQuestion, InterviewSession, InterviewTurn, WeakPoint
from app.schemas.interview import InterviewEvaluationOut
from app.services.interview_context import resolve_domain, search_bank
from app.services.interview_director import choose_from_bank, write_evaluation

logger = logging.getLogger(__name__)

DUPLICATE_RATIO = 0.86
_SAME_TOPIC_RATIO = 0.55  # 同一能力项内的换皮重问，阈值可以更严一点
_VERDICT_SCORE = {"good": 88, "partial": 72, "bad": 45}
_COMPOUND_MARKERS = ("另外", "同时想问", "还想问", "再问", "顺便问", "还有就是", "第二个问题")
# 追问更能证明真实深度：越往下问，权重越高
_DEPTH_WEIGHT = 0.25
_MAX_DEPTH_WEIGHT = 4


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


def too_similar(text: str, turns: list[InterviewTurn], competency: str = "") -> bool:
    """判断是否在换皮重问。

    除了整体相似度，还要拦住"同一能力项里换个说法再问一遍"——
    历史 bug：B+ 树那道题被问了两次，两条 diff 相似度只有 0.63，逃过了 0.86 的阈值。
    """
    candidate = _normalize(text)
    if not candidate:
        return True
    topic = _normalize(competency)
    for turn in turns:
        existing = _normalize(turn.question)
        if not existing:
            continue
        if candidate == existing:
            return True
        ratio = difflib.SequenceMatcher(None, candidate, existing).ratio()
        if ratio >= DUPLICATE_RATIO:
            return True
        same_topic = bool(topic) and (
            topic in _normalize(turn.competency) or _normalize(turn.competency) in topic
        )
        if same_topic and ratio >= _SAME_TOPIC_RATIO:
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
    """把决策变成可直接入库的问题，并处理"复查缺口"的要点注入。"""
    payload = _materialize_payload(db, session=session, decision=decision, turns=turns)
    review_id = getattr(decision, "review_weak_point_id", None)
    payload["review_weak_point_id"] = review_id
    if review_id:
        weak_point = db.get(WeakPoint, int(review_id))
        gap = (weak_point.gap_point or "").strip() if weak_point is not None else ""
        if weak_point is not None and gap:
            points = [str(item) for item in (payload.get("expected_points") or [])]
            payload["expected_points"] = [gap] + [
                item for item in points if item.strip() and item.strip() != gap
            ]
            payload["review_weak_point_id"] = weak_point.id
        else:
            payload["review_weak_point_id"] = None
    return payload


def _materialize_payload(
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
            "followup_kind": getattr(decision, "followup_kind", "") or "deepen",
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
    if too_similar(payload["question"], turns, payload.get("competency") or ""):
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
    rationale = None
    if decision is not None:
        reason = (decision.reason or "").strip()
        if payload["action"] == "followup":
            kind = payload.get("followup_kind") or "deepen"
            rationale = f"[{kind}] {reason}".strip()
        else:
            rationale = reason or None
    turn = InterviewTurn(
        session_id=session.id,
        turn_index=session.asked_count + 1,
        action=payload["action"],
        source=payload["source"],
        parent_turn_id=turns[-1].id if turns and payload["action"] == "followup" else None,
        depth=payload["depth"],
        competency=payload["competency"],
        question=payload["question"],
        rationale=rationale,
        expected_points=payload["expected_points"],
        rubric=payload["rubric"],
        question_id=payload["question_id"],
        claim_id=payload["claim_id"],
        review_weak_point_id=payload.get("review_weak_point_id"),
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


def _turn_score(turn: InterviewTurn) -> int:
    if turn.score is not None:
        return int(turn.score)
    return _VERDICT_SCORE.get(turn.verdict or "", 50)


def competency_scores(turns: list[InterviewTurn]) -> dict[str, float]:
    """按能力项聚合：同一能力项被追问得越深，那一轮权重越高。

    这样"先说对个大概、被追两层就露馅"不会因为轮次多而被平均稀释。
    """
    groups: dict[str, list[tuple[int, float]]] = {}
    for turn in turns:
        if not turn.answer:
            continue
        competency = turn.competency or "综合"
        weight = 1 + _DEPTH_WEIGHT * min(int(turn.depth or 0), _MAX_DEPTH_WEIGHT)
        groups.setdefault(competency, []).append((_turn_score(turn), weight))
    return {
        competency: sum(score * weight for score, weight in items)
        / sum(weight for _, weight in items)
        for competency, items in groups.items()
    }


def _matches_any(competency: str, bucket: set[str]) -> bool:
    """能力项匹配：容忍 "MySQL" / "MySQL索引" 这类包含关系。

    真实判卷里能力项由模型现场命名，完全相等太脆弱——岗位要求写 MySQL，
    轮次写 MySQL索引，不应该被当成两个无关能力。
    """
    name = (competency or "").strip()
    if not name:
        return False
    return any(name == item or name in item or item in name for item in bucket if item)


def _weight_for(competency: str, must: set[str], nice: set[str]) -> float:
    if _matches_any(competency, must):
        return 3.0
    if _matches_any(competency, nice):
        return 1.5
    return 1.0


def _jd_weight_sets(briefing: dict | None) -> tuple[set[str], set[str]]:
    must: set[str] = set()
    nice: set[str] = set()
    for item in (briefing or {}).get("jd_requirements") or []:
        competency = str(item.get("competency") or "").strip()
        if not competency:
            continue
        (must if item.get("kind") == "must" else nice).add(competency)
    return must, nice


def aggregate_score(
    *, turns: list[InterviewTurn], briefing: dict | None
) -> tuple[int, str, list[str], dict[str, float]]:
    """把每轮分数折成一个总分与结论。

    规则（可复算，不依赖模型）：
    1. 先按能力项聚合，追问轮权重更高；
    2. JD 里 must 的能力项权重 3、nice 的 1.5、其余 1；
    3. 硬门槛：must 能力项有作答但低于 55 分，总分封顶 64（真实面试里核心项不过就是不过）；
    4. 信息不足：超过三分之一的问题没答，总分封顶 60。
    """
    answered = [turn for turn in turns if turn.answer]
    per_competency = competency_scores(answered)
    if not per_competency:
        return 0, "fail", ["本场没有有效作答"], {}

    must, nice = _jd_weight_sets(briefing)
    weights = {
        competency: _weight_for(competency, must, nice) for competency in per_competency
    }
    total_weight = sum(weights.values())
    score = round(
        sum(per_competency[c] * weights[c] for c in per_competency) / total_weight
    )
    notes: list[str] = []

    failed_must = [
        competency
        for competency in per_competency
        if _matches_any(competency, must) and per_competency[competency] < 55
    ]
    if failed_must:
        score = min(score, 64)
        notes.append("核心能力未达标：" + "、".join(failed_must))

    unanswered = len([turn for turn in turns if not turn.answer])
    if len(turns) >= 4 and unanswered / len(turns) > 1 / 3:
        score = min(score, 60)
        notes.append(f"{unanswered} 道题未作答，评估信息不足")

    score = max(0, min(100, score))
    decision = (
        "strong_pass" if score >= 85
        else "pass" if score >= 75
        else "borderline" if score >= 65
        else "fail"
    )
    return score, decision, notes, per_competency


def dimension_averages(turns: list[InterviewTurn]) -> dict[str, float]:
    """各维度平均分（原始分点），用于报告里指出短板。"""
    total: dict[str, float] = {}
    count = 0
    for turn in turns:
        if not turn.answer or not isinstance(turn.judgement, dict):
            continue
        dims = turn.judgement.get("dimensions") or {}
        if not dims:
            continue
        count += 1
        for key, value in dims.items():
            total[key] = total.get(key, 0) + float(value or 0)
    if not count:
        return {}
    return {key: round(value / count, 1) for key, value in total.items()}


def build_evaluation(
    db: Session,
    session: InterviewSession,
    *,
    turns: list[InterviewTurn] | None = None,
) -> InterviewEvaluationOut:
    """总分由能力项加权得出（可复算），文案由模型写（失败降级）。"""
    rows = turns if turns is not None else turns_of(db, session.id)
    answered = [turn for turn in rows if turn.answer]

    score, decision, notes, _per_competency = aggregate_score(
        turns=rows, briefing=session.briefing
    )
    dims = dimension_averages(answered)
    unanswered = len([turn for turn in rows if not turn.answer])

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
            turns=rows,
            score=score,
            covered=covered,
            dimensions=dims,
            unanswered=unanswered,
        )
        data = narrative.model_dump()
    except Exception as exc:  # noqa: BLE001  评估文案失败不能把用户卡在面试里
        logger.warning("评估文案生成失败，改用规则摘要：%s", exc)
        data = _heuristic_narrative(rows, score)

    improvements = list(data.get("improvements") or [])
    for note in notes:
        if note not in improvements:
            improvements.append(note)

    dimension_rows = [
        {
            "key": key,
            "label": {
                "coverage": "要点覆盖",
                "specificity": "具体程度",
                "reasoning": "推理深度",
                "authenticity": "经历自证",
                "clarity": "表达结构",
            }.get(key, key),
            "score": value,
            "max": {"coverage": 25, "specificity": 25, "reasoning": 25, "authenticity": 15, "clarity": 10}[key],
        }
        for key, value in dims.items()
    ]

    stats = [
        {"label": "回答轮次", "value": str(len(answered)), "suffix": "轮"},
        {"label": "覆盖能力", "value": str(len(covered)), "suffix": "项"},
        {
            "label": "要点覆盖",
            "value": f"{hits}/{total_points}" if total_points else "—",
            "suffix": "",
        },
        {"label": "追问", "value": str(session.asked_followups), "suffix": "次"},
    ]
    if unanswered:
        stats.append({"label": "未作答", "value": str(unanswered), "suffix": "题"})

    return InterviewEvaluationOut(
        score=score,
        decision=decision,
        headline=data.get("headline") or "本场面试已完成",
        description=data.get("description") or "",
        stats=stats,
        strengths=data.get("strengths") or [],
        improvements=improvements[:5],
        dimensions=dimension_rows,
    )


def close_session(db: Session, session: InterviewSession, *, reason: str) -> None:
    """生成评估并置为 finished；幂等（已有 evaluation 直接返回）。"""
    if session.evaluation:
        return
    turns = turns_of(db, session.id)
    evaluation = build_evaluation(db, session, turns=turns)
    session.status = "finished"
    session.finished_at = datetime.now()
    session.overall_score = evaluation.score
    session.summary = evaluation.description
    session.evaluation = evaluation.model_dump()

    # 成长闭环：把这场暴露的短板沉淀成薄弱点。与评估同事务，
    # 但失败只记日志——不能因为沉淀失败让用户拿不到评估。
    try:
        from app.services.growth import apply_interview_reviews, sync_from_interview

        sync_from_interview(db, session, turns)
        apply_interview_reviews(db, session, turns)
    except Exception:  # 薄弱点沉淀不能阻塞收尾
        logger.exception("薄弱点沉淀失败，已跳过（评估仍然有效）")

    logger.info("session %s 结束（%s），得分 %s", session.id, reason, evaluation.score)
