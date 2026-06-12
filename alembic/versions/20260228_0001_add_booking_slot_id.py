"""add booking slot_id

Revision ID: 20260228_0001
Revises:
Create Date: 2026-02-28 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op  # type: ignore

# revision identifiers, used by Alembic.
revision = "20260228_0001"
down_revision = "4449e6d63f56"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return index_name in {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "bookings"):
        return

    if not _has_column(inspector, "bookings", "slot_id"):
        with op.batch_alter_table("bookings") as batch_op:
            batch_op.add_column(sa.Column("slot_id", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "bookings", "ix_bookings_slot_id"):
        op.create_index("ix_bookings_slot_id", "bookings", ["slot_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "bookings"):
        return

    if _has_index(inspector, "bookings", "ix_bookings_slot_id"):
        op.drop_index("ix_bookings_slot_id", table_name="bookings")

    inspector = sa.inspect(bind)
    if _has_column(inspector, "bookings", "slot_id"):
        with op.batch_alter_table("bookings") as batch_op:
            batch_op.drop_column("slot_id")
