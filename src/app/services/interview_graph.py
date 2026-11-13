"""面试状态图（LangGraph）。

一轮问答被拆成显式节点：

    START → load → (有回答? judge : await)
    judge → director → (search → compose | persist | finish)
    persist → await（interrupt 等候选人）
    finish → END

关键点：
- `interrupt()` 让图真正停在"等回答"，恢复用 `Command(resume=answer)`；
- 状态只放执行位置与中间的判卷/决策，业务事实仍在 MySQL；
- 进程重启后 checkpoint 还在，刷新/掉线都能接着答；
- 没有 checkpoint 时（本地删了文件）退化为"带 answer 的初始状态"，不影响使用。

db 通过 `config["configurable"]["db"]` 注入：节点与调用方共用同一个事务，
判卷失败时整轮一起回滚。
"""

import logging
from contextlib import suppress
from datetime import datetime
from functools import lru_cache
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis import RedisSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import InterviewQuestion, InterviewSession
from app.services import interview_engine as engine
from app.services.interview_context import resolve_domain, search_bank
from app.services.interview_director import (
    DirectorDecision,
    choose_from_bank,
    decide,
)
from app.services.interview_judge import judge_answer

logger = logging.getLogger(__name__)


class InterviewState(TypedDict, total=False):
    """图状态：只放"这一轮"需要的东西，不放 ORM 对象。"""

    session_id: int
    answer: str | None
    judgement: dict
    decision: dict
    candidates: list[int]
    question: dict
    finished: bool
    note: str | None


def _emit(node: str, status: str, **detail) -> None:
    """节点级进度：仅在 SSE 流式调用时有接收方，普通 invoke 自动忽略。"""
    with suppress(Exception):  # 非流式执行时没有 writer
        get_stream_writer()({"node": node, "status": status, "detail": detail})


def _db(config) -> Session:
    db = (config or {}).get("configurable", {}).get("db")
    if db is None:
        raise RuntimeError("图执行缺少 db：请通过 config.configurable.db 注入会话")
    return db


def _session(db: Session, state: InterviewState) -> InterviewSession:
    session = db.get(InterviewSession, state["session_id"])
    if session is None:
        raise RuntimeError("面试会话不存在")
    return session


def _turns(db: Session, session: InterviewSession):
    return engine.turns_of(db, session.id)


# --------------------------------------------------------------------------- #
# 节点
# --------------------------------------------------------------------------- #
def load_context(state: InterviewState, config) -> dict:
    """只做校验与读库；真正的状态都在 MySQL。"""
    session = _session(_db(config), state)
    if session.status != "ongoing":
        raise RuntimeError(f"会话状态不可答：{session.status}")
    return {}


def route_after_load(state: InterviewState) -> str:
    return "judge" if (state.get("answer") or "").strip() else "await"


def _claim_of(session: InterviewSession, claim_id: int | None) -> dict | None:
    """从背景快照里取本轮对应的简历要点，供判卷核对"说的是不是简历里那件事"。"""
    if claim_id is None:
        return None
    for claim in (session.briefing or {}).get("claims") or []:
        if claim.get("id") == claim_id:
            return claim
    return None


def judge_node(state: InterviewState, config) -> dict:
    db = _db(config)
    session = _session(db, state)
    turns = _turns(db, session)
    pending = engine.pending_turn(turns)
    if pending is None:
        # 没有待答题还来判卷，说明前端重复提交或 checkpoint 与库不一致：
        # 宁可报错，也不能凭空再生成一题（历史上出现过同一题被问两遍）
        raise RuntimeError("当前没有待回答的问题，请刷新页面后继续")

    _emit("judge", "start")
    judgement = judge_answer(
        question=pending.question,
        expected_points=list(pending.expected_points or []),
        rubric=dict(pending.rubric or {}),
        answer=state["answer"],
        position=session.position,
        claim=_claim_of(session, pending.claim_id),
        history=[
            {"question": turn.question, "answer": turn.answer, "verdict": turn.verdict}
            for turn in turns
            if turn.answer and turn.id != pending.id
        ][-3:],
        depth=pending.depth,
    )
    pending.answer = state["answer"]
    pending.judgement = judgement.model_dump()
    pending.verdict = judgement.verdict
    pending.score = judgement.score
    pending.answered_at = datetime.now()
    db.flush()
    _emit(
        "judge",
        "done",
        verdict=judgement.verdict,
        score=judgement.score,
        dimensions=judgement.dimensions,
        probe_needed=judgement.probe_needed,
    )
    return {"judgement": judgement.model_dump()}


def director_node(state: InterviewState, config) -> dict:
    db = _db(config)
    session = _session(db, state)
    turns = _turns(db, session)

    if session.asked_count >= session.max_questions:
        _emit("director", "done", action="finish", reason="预算用尽")
        return {
            "decision": {"action": "finish", "reason": "已达到题目预算", "competency": ""}
        }

    _emit("director", "start")
    decision = decide(
        briefing=session.briefing or {},
        turns=turns,
        asked_count=session.asked_count,
        min_questions=session.min_questions,
        max_questions=session.max_questions,
        note=state.get("note"),
    )
    _emit("director", "done", action=decision.action, competency=decision.competency)
    return {"decision": decision.model_dump()}


def route_after_director(state: InterviewState) -> str:
    action = (state.get("decision") or {}).get("action")
    if action == "finish":
        return "finish"
    if action == "search_bank":
        return "search"
    return "persist"


def search_node(state: InterviewState, config) -> dict:
    """题库检索；没有候选时让面试官直接出题，而不是卡住。"""
    db = _db(config)
    session = _session(db, state)
    turns = _turns(db, session)
    decision = DirectorDecision(**state["decision"])

    _emit("search", "start")
    used_ids = {turn.question_id for turn in turns if turn.question_id is not None}
    candidates = search_bank(
        db,
        domain=(session.briefing or {}).get("domain") or resolve_domain(session.position),
        query=decision.search_query or decision.competency or "",
        competency=decision.search_competency or decision.competency or None,
        difficulty=decision.search_difficulty,
        exclude_ids=used_ids,
        limit=5,
    )
    if not candidates:
        logger.info("题库无候选，改为现场提问")
        retry = decide(
            briefing=session.briefing or {},
            turns=turns,
            asked_count=session.asked_count,
            min_questions=session.min_questions,
            max_questions=session.max_questions,
            note="题库没有合适的候选题，请直接根据简历或岗位要求提问",
        )
        if retry.action == "search_bank":
            retry = retry.model_copy(
                update={
                    "action": "ask",
                    "question": f"我们聊聊{decision.search_competency or decision.competency or '你的项目'}，"
                    "你在实际项目里是怎么用的？",
                }
            )
        return {"decision": retry.model_dump(), "candidates": []}

    _emit("search", "done", candidates=len(candidates))
    return {"candidates": [question.id for question in candidates], "note": None}


def route_after_search(state: InterviewState) -> str:
    return "compose" if state.get("candidates") else "persist"


def compose_node(state: InterviewState, config) -> dict:
    """从候选里挑一道并改写成口语提问；rubric 以数据库为准。"""
    db = _db(config)
    session = _session(db, state)
    turns = _turns(db, session)
    decision = DirectorDecision(**state["decision"])

    _emit("compose", "start")
    questions = [
        question
        for question in (db.get(InterviewQuestion, qid) for qid in state["candidates"])
        if question is not None
    ]
    choice = choose_from_bank(
        briefing=session.briefing or {},
        turns=turns,
        decision=decision,
        candidates=questions,
    )
    payload = engine.payload_from_bank_choice(db, decision=decision, choice=choice)
    _emit("compose", "done", question=payload["question"][:60])
    return {"question": payload}


def persist_node(state: InterviewState, config) -> dict:
    """把决策落成一轮问题；重复/复合问句带提示重来一次。"""
    db = _db(config)
    session = _session(db, state)
    turns = _turns(db, session)
    decision = DirectorDecision(**state["decision"])

    _emit("persist", "start")

    # 不变量：一题未答就不能再出新题。前端重复提交或 checkpoint 与库不一致时，
    # 这里曾生成过"同一道题问两遍"，宁可把原题返回去也不能加题。
    pending = engine.pending_turn(turns)
    if pending is not None:
        logger.warning(
            "turn %s 仍未作答，跳过出题，继续等待同一个问题", pending.turn_index
        )
        return {
            "question": {"question": pending.question, "competency": pending.competency},
            "finished": False,
            "turn_id": pending.id,
        }

    payload = state.get("question") or engine.materialize(
        db, session=session, decision=decision, turns=turns
    )
    problem = engine.payload_problem(payload, turns)
    if problem:
        logger.info("问题未通过校验，带提示重来：%s", problem)
        decision = decide(
            briefing=session.briefing or {},
            turns=turns,
            asked_count=session.asked_count,
            min_questions=session.min_questions,
            max_questions=session.max_questions,
            note=problem,
        )
        if decision.action == "finish":
            # 重来一次后决定收尾：直接结束，不能停在一个不存在的问题上
            return {"decision": decision.model_dump(), "finished": True}
        payload = engine.materialize(
            db, session=session, decision=decision, turns=turns
        )
        again = engine.payload_problem(payload, turns)
        if again:
            raise RuntimeError(f"面试官连续两次没有给出可用的新问题：{again}")

    turn = engine.create_turn(
        db, session, turns=turns, decision=decision, payload=payload
    )
    _emit("persist", "done", turn_index=turn.turn_index, competency=turn.competency)
    return {
        "question": payload,
        "decision": decision.model_dump(),
        "finished": False,
        "turn_id": turn.id,
    }


def route_after_persist(state: InterviewState) -> str:
    return "finish" if state.get("finished") else "await"


def finish_node(state: InterviewState, config) -> dict:
    db = _db(config)
    session = _session(db, state)
    _emit("finish", "start")
    engine.close_session(db, session, reason="director")
    logger.info("session %s 由图收尾", session.id)
    _emit("finish", "done", score=session.overall_score)
    return {"finished": True}


def await_node(state: InterviewState, config) -> dict:
    """停在等待候选人作答；恢复时 interrupt() 返回 answer。"""
    payload = interrupt(
        {
            "session_id": state["session_id"],
            "stage": "await_answer",
        }
    )
    answer = payload.get("answer") if isinstance(payload, dict) else payload
    return {"answer": str(answer or "").strip(), "note": None}


# --------------------------------------------------------------------------- #
# 构图
# --------------------------------------------------------------------------- #
def build_graph(checkpointer=None):
    graph = StateGraph(InterviewState)
    graph.add_node("load", load_context)
    graph.add_node("judge", judge_node)
    graph.add_node("director", director_node)
    graph.add_node("search", search_node)
    graph.add_node("compose", compose_node)
    graph.add_node("persist", persist_node)
    graph.add_node("await", await_node)
    graph.add_node("finish", finish_node)

    graph.add_edge(START, "load")
    graph.add_conditional_edges("load", route_after_load, {"judge": "judge", "await": "await"})
    graph.add_edge("judge", "director")
    graph.add_conditional_edges(
        "director",
        route_after_director,
        {"search": "search", "persist": "persist", "finish": "finish"},
    )
    graph.add_conditional_edges(
        "search", route_after_search, {"compose": "compose", "persist": "persist"}
    )
    graph.add_edge("compose", "persist")
    graph.add_conditional_edges(
        "persist", route_after_persist, {"await": "await", "finish": "finish"}
    )
    graph.add_edge("await", "load")
    graph.add_edge("finish", END)

    return graph.compile(checkpointer=checkpointer)


def _build_checkpointer():
    """Redis 持久化执行位置；不可用时退化为内存（仍能靠 MySQL 重建）。

    RedisSaver 依赖 RedisJSON + RediSearch；Redis 8 已内置这两个模块。
    TTL 让过期的面试 checkpoint 自动清理，不必手工归档。
    """
    try:
        saver = RedisSaver(
            redis_url=settings.REDIS_URL,
            ttl={
                "default_ttl": settings.CHECKPOINT_TTL_MINUTES,
                "refresh_on_read": True,
            },
        )
        saver.setup()
        logger.info("面试图 checkpointer: redis %s", settings.REDIS_URL)
        return saver
    except Exception as exc:  # noqa: BLE001  没有持久化也要能面试
        logger.warning("Redis checkpointer 不可用，改用内存：%s", exc)
        return InMemorySaver()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph(_build_checkpointer())


def graph_config(db: Session, session_id: int) -> dict:
    return {"configurable": {"thread_id": str(session_id), "db": db}}


def start_session(db: Session, session_id: int) -> None:
    """建会话后跑一次图：走到 await 处停住，顺便建立 checkpoint。"""
    get_graph().invoke({"session_id": session_id}, graph_config(db, session_id))


def stream_answer_events(db: Session, session_id: int, answer: str):
    """逐节点产出事件；调用方负责把 custom 事件转成 SSE。"""
    graph = get_graph()
    config = graph_config(db, session_id)
    snapshot = graph.get_state(config)
    # 只认"停在某个节点上"的 checkpoint（next 非空）。
    # 图已经跑到 END 的线程再 resume 不会报错，而是静默返回终态——
    # 上一轮事务回滚后可能出现这种"checkpoint 比 MySQL 走得快"的情况。
    if snapshot.values and snapshot.next:
        payload = Command(resume={"answer": answer})
    else:
        logger.info("session %s 没有可续跑的 checkpoint，按初始状态执行", session_id)
        payload = {"session_id": session_id, "answer": answer}

    yield from graph.stream(payload, config, stream_mode=["updates", "custom"])


def resume_with_answer(db: Session, session_id: int, answer: str) -> None:
    """提交回答：有可续跑的 checkpoint 就 resume，否则用初始状态带 answer 跑。"""
    graph = get_graph()
    config = graph_config(db, session_id)
    snapshot = graph.get_state(config)
    if snapshot.values and snapshot.next:
        graph.invoke(Command(resume={"answer": answer}), config)
    else:
        logger.info("session %s 没有可续跑的 checkpoint，按初始状态执行", session_id)
        graph.invoke({"session_id": session_id, "answer": answer}, config)
