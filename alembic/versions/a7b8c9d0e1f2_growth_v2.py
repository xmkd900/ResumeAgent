"""growth loop v2: gap fixing + spaced review

把"薄弱点"从"一个主题 + 掌握度"改成"一条具体缺口 + 修复/复查状态"：
- weak_point 记录缺口原文、来源轮次、状态机与复习排期
- weak_point_practice 记录动作类型（fix/review/legacy）与缺口是否补上

Revision ID: a7b8c9d0e1f2
Revises: c4a1e8f2b6d0
Create Date: 2026-11-17 17:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "c4a1e8f2b6d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weak_point",
        sa.Column(
            "source_turn_id",
            sa.Integer(),
            nullable=True,
            comment="缺口来源轮次：用于回放原题、原回答与原缺口",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "gap_point",
            sa.Text(),
            nullable=True,
            comment="具体缺的那一条要点（来自判卷的缺失/部分覆盖项）",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "gap_quote",
            sa.Text(),
            nullable=True,
            comment="候选人当时与此缺口相关的原话（可为空）",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="open",
            comment="状态：open 待修复 / fixed 待复查 / resolved 已掌握",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "review_stage",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="复习阶段：0 未开始，1..N 对应 1/3/7/14/30 天",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "next_review_at",
            sa.DateTime(),
            nullable=True,
            comment="下次复习时间；为空表示暂不排期",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "last_reviewed_at",
            sa.DateTime(),
            nullable=True,
            comment="最近一次复查时间",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "fix_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="累计修复次数（改写/补一句）",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "review_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="累计复查次数（变体题复测）",
        ),
    )
    op.create_foreign_key(
        "fk_weak_source_turn",
        "weak_point",
        "interview_turn",
        ["source_turn_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_weak_user_review",
        "weak_point",
        ["user_id", "status", "next_review_at"],
        unique=False,
    )

    # 存量数据：已掌握的置 resolved，其余待修复；缺口先沿用 last_evidence
    op.execute("UPDATE weak_point SET status = 'resolved' WHERE resolved = 1")
    op.execute(
        "UPDATE weak_point SET gap_point = last_evidence "
        "WHERE gap_point IS NULL AND last_evidence IS NOT NULL"
    )

    op.add_column(
        "weak_point_practice",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="legacy",
            comment="动作类型：fix 修复 / review 复查 / legacy 旧版练习",
        ),
    )
    op.add_column(
        "weak_point_practice",
        sa.Column(
            "gap_covered",
            sa.Boolean(),
            nullable=True,
            comment="本条缺口是否补上（fix/review 的结果；legacy 为空）",
        ),
    )
    op.add_column(
        "weak_point_practice",
        sa.Column(
            "stage_before",
            sa.Integer(),
            nullable=True,
            comment="本次动作前的复习阶段",
        ),
    )
    op.add_column(
        "weak_point_practice",
        sa.Column(
            "stage_after",
            sa.Integer(),
            nullable=True,
            comment="本次动作后的复习阶段",
        ),
    )


def downgrade() -> None:
    op.drop_column("weak_point_practice", "stage_after")
    op.drop_column("weak_point_practice", "stage_before")
    op.drop_column("weak_point_practice", "gap_covered")
    op.drop_column("weak_point_practice", "kind")

    op.drop_index("ix_weak_user_review", table_name="weak_point")
    op.drop_constraint("fk_weak_source_turn", "weak_point", type_="foreignkey")
    op.drop_column("weak_point", "review_count")
    op.drop_column("weak_point", "fix_count")
    op.drop_column("weak_point", "last_reviewed_at")
    op.drop_column("weak_point", "next_review_at")
    op.drop_column("weak_point", "review_stage")
    op.drop_column("weak_point", "status")
    op.drop_column("weak_point", "gap_quote")
    op.drop_column("weak_point", "gap_point")
    op.drop_column("weak_point", "source_turn_id")
