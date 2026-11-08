"""agentic interview loop

把"预生成整卷"改为"每轮由面试官决策"：
- 新增 interview_turn（一轮问答一行，含决策理由与判卷）
- interview_session 去掉 question_plan/total_questions/current_*，改为预算与背景快照
- 旧 interview_message 的数据回填进 interview_turn 后再删除，历史面试不丢

Revision ID: 7f94d5abc7df
Revises: 7860e668f8ef
Create Date: 2026-11-06 18:13:22.293364
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f94d5abc7df"
down_revision: str | Sequence[str] | None = "7860e668f8ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VERDICT_SCORE = {"good": 88, "partial": 72, "bad": 45}


def _json(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _backfill_turns(bind) -> None:
    """把旧的 interviewer/candidate 消息两两配对成 turn。"""
    sessions = bind.execute(
        sa.text("select id, question_plan, total_questions, started_at from interview_session")
    ).mappings().all()
    if not sessions:
        return

    plan_slots: dict[int, dict[int, dict]] = {}
    session_meta: dict[int, dict] = {}
    for row in sessions:
        session_meta[row["id"]] = {
            "total": row["total_questions"] or 0,
            "started_at": row["started_at"],
        }
        slots: dict[int, dict] = {}
        raw = row["question_plan"]
        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                for slot in data.get("slots") or []:
                    bank_id = slot.get("bank_id")
                    if bank_id is not None:
                        slots[int(bank_id)] = slot
            except (ValueError, TypeError, AttributeError):
                slots = {}
        plan_slots[row["id"]] = slots

    messages = bind.execute(
        sa.text(
            "select id, session_id, round, role, content, question_id, depth, "
            "judgement, created_at from interview_message "
            "order by session_id, round, id"
        )
    ).mappings().all()

    grouped: dict[int, list] = {}
    for message in messages:
        grouped.setdefault(message["session_id"], []).append(message)

    for session_id, rows in grouped.items():
        slots = plan_slots.get(session_id, {})
        counter = 0
        pending = None
        competencies: list[str] = []
        followups = 0

        for message in rows:
            if message["role"] == "interviewer":
                counter += 1
                slot = slots.get(message["question_id"] or -1, {})
                competency = slot.get("competency") or ""
                depth = message["depth"] or 0
                if depth > 0:
                    followups += 1
                elif competency:
                    competencies.append(competency)

                result = bind.execute(
                    sa.text(
                        "insert into interview_turn "
                        "(session_id, turn_index, action, source, parent_turn_id, depth, "
                        " competency, question, rationale, expected_points, rubric, "
                        " question_id, claim_id, created_at) "
                        "values (:session_id, :turn_index, :action, :source, :parent_turn_id, "
                        " :depth, :competency, :question, :rationale, :expected_points, :rubric, "
                        " :question_id, :claim_id, :created_at)"
                    ),
                    {
                        "session_id": session_id,
                        "turn_index": counter,
                        "action": "legacy",
                        "source": slot.get("source") or "bank",
                        "parent_turn_id": pending["id"] if pending and depth > 0 else None,
                        "depth": depth,
                        "competency": competency,
                        "question": message["content"] or "",
                        "rationale": "旧版计划式会话回填",
                        "expected_points": _json(slot.get("expected_points") or []),
                        "rubric": _json(slot.get("rubric") or {}),
                        "question_id": message["question_id"],
                        "claim_id": slot.get("claim_id"),
                        "created_at": message["created_at"],
                    },
                )
                pending = {"id": result.lastrowid}
                continue

            if message["role"] != "candidate" or pending is None:
                continue

            judgement = message["judgement"]
            if isinstance(judgement, str):
                try:
                    judgement = json.loads(judgement)
                except ValueError:
                    judgement = None
            verdict = (judgement or {}).get("verdict")
            score = (judgement or {}).get("score")
            if score is None and verdict:
                score = _VERDICT_SCORE.get(verdict)

            bind.execute(
                sa.text(
                    "update interview_turn set answer = :answer, judgement = :judgement, "
                    "verdict = :verdict, score = :score, answered_at = :answered_at "
                    "where id = :id"
                ),
                {
                    "answer": message["content"],
                    "judgement": _json(judgement),
                    "verdict": verdict,
                    "score": score,
                    "answered_at": message["created_at"],
                    "id": pending["id"],
                },
            )
            pending = None

        meta = session_meta.get(session_id, {})
        total = max(int(meta.get("total") or 0), counter)
        bind.execute(
            sa.text(
                "update interview_session set asked_count = :asked, asked_followups = :followups, "
                "max_questions = :max_q, min_questions = 1, coverage = :coverage, "
                "prompt_version = 'legacy-plan' where id = :id"
            ),
            {
                "asked": counter,
                "followups": followups,
                "max_q": max(1, total),
                "coverage": _json(
                    {"competencies": list(dict.fromkeys(competencies)), "claim_ids": []}
                ),
                "id": session_id,
            },
        )


def upgrade() -> None:
    op.add_column("interview_session", sa.Column("jd_text", sa.Text(), nullable=True))
    op.add_column(
        "interview_session",
        sa.Column("max_questions", sa.Integer(), nullable=False, server_default=sa.text("12")),
    )
    op.add_column(
        "interview_session",
        sa.Column("min_questions", sa.Integer(), nullable=False, server_default=sa.text("4")),
    )
    op.add_column(
        "interview_session",
        sa.Column("asked_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "interview_session",
        sa.Column("asked_followups", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("interview_session", sa.Column("briefing", sa.JSON(), nullable=True))
    op.add_column("interview_session", sa.Column("coverage", sa.JSON(), nullable=True))
    op.add_column(
        "interview_session",
        sa.Column(
            "prompt_version", sa.String(length=32), nullable=False, server_default="director-v1"
        ),
    )

    op.create_table(
        "interview_turn",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("parent_turn_id", sa.Integer(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("competency", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("expected_points", sa.JSON(), nullable=True),
        sa.Column("rubric", sa.JSON(), nullable=True),
        sa.Column("question_id", sa.Integer(), nullable=True),
        sa.Column("claim_id", sa.Integer(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("judgement", sa.JSON(), nullable=True),
        sa.Column("verdict", sa.String(length=16), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_turn_id"], ["interview_turn.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["interview_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_turn_question", "interview_turn", ["question_id"], unique=False)
    op.create_index(
        "ix_turn_session_index", "interview_turn", ["session_id", "turn_index"], unique=False
    )

    # 历史会话先回填，避免删表时丢掉用户的面试记录
    _backfill_turns(op.get_bind())

    # 索引被外键占用，直接删表即可（索引随表一起消失）
    op.drop_table("interview_message")

    op.drop_column("interview_session", "question_plan")
    op.drop_column("interview_session", "current_index")
    op.drop_column("interview_session", "current_depth")
    op.drop_column("interview_session", "total_questions")

    # 运行时由 Python 侧 default 提供，去掉 DB 默认值避免 schema 漂移
    for column in ("max_questions", "min_questions", "asked_count", "asked_followups", "prompt_version"):
        op.alter_column("interview_session", column, server_default=None)


def downgrade() -> None:
    op.add_column(
        "interview_session",
        sa.Column("total_questions", mysql.INTEGER(), autoincrement=False, nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "interview_session",
        sa.Column("current_depth", mysql.INTEGER(), autoincrement=False, nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "interview_session",
        sa.Column("current_index", mysql.INTEGER(), autoincrement=False, nullable=False, server_default=sa.text("0")),
    )
    op.add_column("interview_session", sa.Column("question_plan", mysql.JSON(), nullable=True))
    op.drop_column("interview_session", "prompt_version")
    op.drop_column("interview_session", "coverage")
    op.drop_column("interview_session", "briefing")
    op.drop_column("interview_session", "asked_followups")
    op.drop_column("interview_session", "asked_count")
    op.drop_column("interview_session", "min_questions")
    op.drop_column("interview_session", "max_questions")
    op.drop_column("interview_session", "jd_text")

    op.create_table(
        "interview_message",
        sa.Column("id", mysql.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("session_id", mysql.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("round", mysql.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("role", mysql.VARCHAR(length=16), nullable=False),
        sa.Column("content", mysql.TEXT(), nullable=False),
        sa.Column("question_id", mysql.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("parent_message_id", mysql.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("depth", mysql.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("judgement", mysql.JSON(), nullable=True),
        sa.Column("trace", mysql.JSON(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(), server_default=sa.text("(now())"), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_message_id"], ["interview_message.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["session_id"], ["interview_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_message_session_round"), "interview_message", ["session_id", "round"], unique=False
    )
    op.drop_index("ix_turn_session_index", table_name="interview_turn")
    op.drop_index("ix_turn_question", table_name="interview_turn")
    op.drop_table("interview_turn")
