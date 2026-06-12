"""add payment status to bookings

Revision ID: 4f8825837953
Revises: 6a47defd100a
Create Date: 2026-03-14 17:20:23.379711
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '4f8825837953'
down_revision = '6a47defd100a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("payment_status", sa.String(length=20), nullable=False, server_default="unpaid"),
    )
    op.create_index(op.f("ix_bookings_payment_status"), "bookings", ["payment_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bookings_payment_status"), table_name="bookings")
    op.drop_column("bookings", "payment_status")
