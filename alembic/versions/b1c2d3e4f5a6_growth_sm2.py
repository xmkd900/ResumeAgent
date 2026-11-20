"""growth v2 followups: SM-2 schedule + interview review link

- weak_point 增加 interval_days / ease_factor，复习间隔不再固定 1/3/7/14/30
- interview_turn 增加 review_weak_point_id，让"面试复查"能回写到具体缺口

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-11-20 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weak_point",
        sa.Column(
            "interval_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="当前复习间隔（天），SM-2 用它推算下一次",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "ease_factor",
            sa.Float(),
            nullable=False,
            server_default="2.5",
            comment="SM-2 难度因子：答得好上升、答得差下降（下限 1.3）",
        ),
    )
    op.add_column(
        "interview_turn",
        sa.Column(
            "review_weak_point_id",
            sa.Integer(),
            nullable=True,
            comment="本轮是复查哪条缺口（面试闭环回写用；不加外键，避免与 weak_point.source_turn_id 形成循环依赖）",
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_turn", "review_weak_point_id")
    op.drop_column("weak_point", "ease_factor")
    op.drop_column("weak_point", "interval_days")
