"""add product store prices

Revision ID: 33a5d9c12b4f
Revises: 7e90d6e2e6a3
Create Date: 2026-03-03 10:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "33a5d9c12b4f"
down_revision: Union[str, Sequence[str], None] = "7e90d6e2e6a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stores", sa.Column("kroger_location_id", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_stores_kroger_location_id"), "stores", ["kroger_location_id"], unique=True)

    op.create_table(
        "product_store_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "store_id", name="uq_product_store_price"),
    )
    op.create_index(
        op.f("ix_product_store_prices_id"),
        "product_store_prices",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_store_prices_product_id"),
        "product_store_prices",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_store_prices_store_id"),
        "product_store_prices",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_store_prices_last_updated"),
        "product_store_prices",
        ["last_updated"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_product_store_prices_last_updated"), table_name="product_store_prices")
    op.drop_index(op.f("ix_product_store_prices_store_id"), table_name="product_store_prices")
    op.drop_index(op.f("ix_product_store_prices_product_id"), table_name="product_store_prices")
    op.drop_index(op.f("ix_product_store_prices_id"), table_name="product_store_prices")
    op.drop_table("product_store_prices")

    op.drop_index(op.f("ix_stores_kroger_location_id"), table_name="stores")
    op.drop_column("stores", "kroger_location_id")
