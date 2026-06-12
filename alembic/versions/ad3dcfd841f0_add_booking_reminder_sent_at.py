"""add booking reminder sent at

Revision ID: ad3dcfd841f0
Revises: 4f8825837953
Create Date: 2026-03-18 16:03:44.633419
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'ad3dcfd841f0'
down_revision = '4f8825837953'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("reminder_sent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "reminder_sent_at")
