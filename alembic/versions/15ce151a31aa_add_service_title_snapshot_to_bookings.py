"""add service title snapshot to bookings

Revision ID: 15ce151a31aa
Revises: cba703da3b49
Create Date: 2026-03-20 20:34:30.752460
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "15ce151a31aa"
down_revision = "cba703da3b49"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("service_title_snapshot", sa.String(length=150), nullable=True),
    )

    op.execute(
        """
        UPDATE bookings
        SET service_title_snapshot = (
            SELECT services.title
            FROM services
            WHERE services.id = bookings.service_id
        )
        """
    )

    with op.batch_alter_table("bookings") as batch_op:
        batch_op.alter_column(
            "service_title_snapshot",
            existing_type=sa.String(length=150),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.drop_column("service_title_snapshot")