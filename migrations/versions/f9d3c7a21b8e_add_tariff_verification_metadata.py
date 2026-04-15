"""add tariff verification metadata

Revision ID: f9d3c7a21b8e
Revises: 33a5d9c12b4f
Create Date: 2026-04-15 11:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9d3c7a21b8e"
down_revision: Union[str, Sequence[str], None] = "33a5d9c12b4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "products",
        sa.Column("rate_type", sa.String(length=20), nullable=False, server_default="duty_free"),
    )
    op.add_column("products", sa.Column("specific_duty_value", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("source_url", sa.String(length=500), nullable=True))
    op.add_column("products", sa.Column("verification_source", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("verification_notes", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "products",
        sa.Column(
            "confidence_score",
            sa.DECIMAL(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
    )
    op.add_column(
        "products",
        sa.Column("review_status", sa.String(length=20), nullable=False, server_default="incomplete"),
    )
    op.add_column(
        "products",
        sa.Column(
            "manual_tariff_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_index(op.f("ix_products_verified_at"), "products", ["verified_at"], unique=False)
    op.create_index(op.f("ix_products_review_status"), "products", ["review_status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_products_review_status"), table_name="products")
    op.drop_index(op.f("ix_products_verified_at"), table_name="products")

    op.drop_column("products", "manual_tariff_override")
    op.drop_column("products", "review_status")
    op.drop_column("products", "confidence_score")
    op.drop_column("products", "verified_at")
    op.drop_column("products", "verification_notes")
    op.drop_column("products", "verification_source")
    op.drop_column("products", "source_url")
    op.drop_column("products", "specific_duty_value")
    op.drop_column("products", "rate_type")
