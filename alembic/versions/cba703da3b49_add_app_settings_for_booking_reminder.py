"""add app settings for booking reminder

Revision ID: cba703da3b49
Revises: ad3dcfd841f0
Create Date: 2026-03-19 11:51:23.486531
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'cba703da3b49'
down_revision = 'ad3dcfd841f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_app_settings_key"), "app_settings", ["key"], unique=True)

    op.execute(
    """
    INSERT INTO app_settings (key, value, created, updated)
    VALUES ('booking_reminder_lead_minutes', '60', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
)

def downgrade() -> None:
    op.drop_index(op.f("ix_app_settings_key"), table_name="app_settings")
    op.drop_table("app_settings")