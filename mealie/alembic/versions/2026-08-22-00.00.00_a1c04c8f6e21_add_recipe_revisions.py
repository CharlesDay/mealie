"""add recipe revisions

Revision ID: a1c04c8f6e21
Revises: 2187537c52b8
Create Date: 2026-08-22 00:00:00
"""

import sqlalchemy as sa
from alembic import op

import mealie.db.migration_types

revision = "a1c04c8f6e21"
down_revision: str | None = "2187537c52b8"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_revisions",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("recipe_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("user_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recipe_revisions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_recipe_revisions_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_recipe_revisions_recipe_id"), ["recipe_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_recipe_revisions_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("recipe_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipe_revisions_user_id"))
        batch_op.drop_index(batch_op.f("ix_recipe_revisions_recipe_id"))
        batch_op.drop_index(batch_op.f("ix_recipe_revisions_created_at"))
    op.drop_table("recipe_revisions")
