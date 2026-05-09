"""Create claims.lost_item, claims.claim, claims.poll_state

Revision ID: 0002_lost_item_claim_poll
Revises: 0001_seller_profile
Create Date: 2026-05-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_lost_item_claim_poll"
down_revision: Union[str, None] = "0001_seller_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "claims"


def upgrade() -> None:
    # Claim table first — lost_item.claim_id FKs into it.
    op.create_table(
        "claim",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_amount", sa.BigInteger(), nullable=True),
        sa.Column("total_qty", sa.Integer(), nullable=True),
        sa.Column("generated_docx_path", sa.Text(), nullable=True),
        sa.Column("generated_agreement_path", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_claim_user", "claim", ["user_id"], schema=SCHEMA)

    op.create_table(
        "lost_item",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("loss_type", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("uzum_sku_id", sa.BigInteger(), nullable=True),
        sa.Column("barcode", sa.Text(), nullable=True),
        sa.Column("product_title", sa.Text(), nullable=True),
        sa.Column("expected_qty", sa.Integer(), nullable=False),
        sa.Column("received_qty", sa.Integer(), nullable=True),
        sa.Column("unit_price", sa.BigInteger(), nullable=True),
        sa.Column("unit_compensation", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "claim_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.claim.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_lost_item_user_claim", "lost_item", ["user_id", "claim_id"], schema=SCHEMA)
    op.create_unique_constraint(
        "uq_lost_item_dedup",
        "lost_item",
        ["user_id", "source_ref", "loss_type"],
        schema=SCHEMA,
    )

    op.create_table(
        "poll_state",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cursor", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "shop_id", "source"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("poll_state", schema=SCHEMA)
    op.drop_table("lost_item", schema=SCHEMA)
    op.drop_table("claim", schema=SCHEMA)
