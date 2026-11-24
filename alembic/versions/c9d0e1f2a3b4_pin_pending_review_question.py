"""pin pending review question

复查题必须"看哪道就判哪道"：把已选定的题落库，避免提交时重新选题
（改写题每次调用模型都不同，会导致题面与判卷不一致）。

Revision ID: c9d0e1f2a3b4
Revises: b1c2d3e4f5a6
Create Date: 2026-11-20 19:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weak_point",
        sa.Column(
            "pending_review_question_id",
            sa.Integer(),
            nullable=True,
            comment="已选定的复查题 ID（题库题；改写题为空）",
        ),
    )
    op.add_column(
        "weak_point",
        sa.Column(
            "pending_review_question_text",
            sa.Text(),
            nullable=True,
            comment="已选定的复查题面（改写题同样落库，避免刷新后换题）",
        ),
    )


def downgrade() -> None:
    op.drop_column("weak_point", "pending_review_question_text")
    op.drop_column("weak_point", "pending_review_question_id")
