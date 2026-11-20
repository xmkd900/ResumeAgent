"""growth loop

成长闭环落地：
- 新增 weak_point：跨面试累积的薄弱点（(user_id, topic) 唯一，复发只累加不插行）
- 新增 weak_point_practice：练习记录（掌握度变化可追溯，也是"近 7 天练习"的数据源）

Revision ID: 9d3c7b51a2f4
Revises: ba3bf953043e
Create Date: 2026-11-15 16:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9d3c7b51a2f4"
down_revision: str | Sequence[str] | None = "ba3bf953043e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weak_point",
        sa.Column(
            "id", sa.Integer(), autoincrement=True, nullable=False, comment="薄弱点 ID，自增主键"
        ),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="所属用户 ID"),
        sa.Column(
            "topic",
            sa.String(length=128),
            nullable=False,
            comment="知识点主题，同一用户内唯一（如 MySQL索引）",
        ),
        sa.Column(
            "domain",
            sa.String(length=32),
            nullable=False,
            server_default="backend",
            comment="所属领域：backend/frontend/agent/common",
        ),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="interview",
            comment="来源：interview 面试暴露 / self_test 自测暴露",
        ),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=False,
            server_default="medium",
            comment="严重度：low / medium / high",
        ),
        sa.Column(
            "relapse_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="复发次数：再次被面试判为薄弱时 +1",
        ),
        sa.Column(
            "mastery_score",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="掌握度 0-100，由练习判卷按固定公式更新（模型不直接给）",
        ),
        sa.Column(
            "resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
            comment="是否已标记掌握；复发时重新置 0",
        ),
        sa.Column("related_tags", sa.JSON(), nullable=True, comment="关联标签，用于题库练习推荐"),
        sa.Column(
            "last_evidence",
            sa.Text(),
            nullable=True,
            comment="最近一次暴露的具体缺口（判卷 missing_points 或反馈摘要）",
        ),
        sa.Column(
            "last_session_id",
            sa.Integer(),
            nullable=True,
            comment="最近一次暴露该短板的面试会话 ID",
        ),
        sa.Column(
            "practice_count", sa.Integer(), nullable=False, server_default="0", comment="累计练习次数"
        ),
        sa.Column("last_practiced_at", sa.DateTime(), nullable=True, comment="最近一次练习时间"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="最后更新时间",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_session_id"], ["interview_session.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "topic", name="uk_weak_user_topic"),
        comment="薄弱点：跨面试累积的能力短板、复发次数与掌握度",
    )
    op.create_index(
        "ix_weak_user_state", "weak_point", ["user_id", "resolved", "severity"], unique=False
    )

    op.create_table(
        "weak_point_practice",
        sa.Column(
            "id", sa.Integer(), autoincrement=True, nullable=False, comment="练习记录 ID，自增主键"
        ),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="所属用户 ID"),
        sa.Column("weak_point_id", sa.Integer(), nullable=False, comment="所属薄弱点 ID"),
        sa.Column("question_id", sa.Integer(), nullable=True, comment="题库题 ID（自拟的复述题为空）"),
        sa.Column("question", sa.Text(), nullable=False, comment="本轮练习题目"),
        sa.Column("answer", sa.Text(), nullable=False, comment="候选人复述内容"),
        sa.Column(
            "verdict", sa.String(length=16), nullable=False, comment="判卷档位：good / partial / bad"
        ),
        sa.Column("score", sa.Integer(), nullable=False, comment="本轮得分 0-100"),
        sa.Column("mastery_before", sa.Integer(), nullable=False, comment="练习前的掌握度"),
        sa.Column("mastery_after", sa.Integer(), nullable=False, comment="练习后的掌握度"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="练习时间",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["weak_point_id"], ["weak_point.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="薄弱点练习记录：问题、回答、判卷与掌握度变化",
    )
    op.create_index(
        "ix_practice_user_time",
        "weak_point_practice",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_practice_point_time",
        "weak_point_practice",
        ["weak_point_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_practice_point_time", table_name="weak_point_practice")
    op.drop_index("ix_practice_user_time", table_name="weak_point_practice")
    op.drop_table("weak_point_practice")
    op.drop_index("ix_weak_user_state", table_name="weak_point")
    op.drop_table("weak_point")
