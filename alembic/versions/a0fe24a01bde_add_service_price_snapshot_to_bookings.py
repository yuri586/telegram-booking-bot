"""add service price snapshot to bookings

Revision ID: a0fe24a01bde
Revises: 15ce151a31aa
Create Date: 2026-03-22 18:58:10.303458
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'a0fe24a01bde'
down_revision = '15ce151a31aa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("service_price_snapshot", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "service_price_snapshot")
