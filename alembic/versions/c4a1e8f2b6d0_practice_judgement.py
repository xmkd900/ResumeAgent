"""store practice judgement

练习记录补存完整判卷明细，便于复盘"为什么这题判低了"。

Revision ID: c4a1e8f2b6d0
Revises: 9d3c7b51a2f4
Create Date: 2026-11-16 16:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4a1e8f2b6d0"
down_revision: str | Sequence[str] | None = "9d3c7b51a2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weak_point_practice",
        sa.Column(
            "judgement",
            sa.JSON(),
            nullable=True,
            comment="完整判卷明细：逐要点判定、命中/部分覆盖/缺失与原文引用",
        ),
    )


def downgrade() -> None:
    op.drop_column("weak_point_practice", "judgement")
