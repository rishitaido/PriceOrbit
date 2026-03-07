"""add stores table

Revision ID: 7e90d6e2e6a3
Revises: bf251f5767b3
Create Date: 2026-03-03 09:25:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7e90d6e2e6a3"
down_revision: Union[str, Sequence[str], None] = "bf251f5767b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("zip_code", sa.String(length=10), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("phone", sa.String(length=25), nullable=True),
        sa.Column("hours", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stores_id"), "stores", ["id"], unique=False)
    op.create_index(op.f("ix_stores_name"), "stores", ["name"], unique=False)
    op.create_index(op.f("ix_stores_city"), "stores", ["city"], unique=False)
    op.create_index(op.f("ix_stores_state"), "stores", ["state"], unique=False)
    op.create_index(op.f("ix_stores_zip_code"), "stores", ["zip_code"], unique=False)
    op.create_index(op.f("ix_stores_latitude"), "stores", ["latitude"], unique=False)
    op.create_index(op.f("ix_stores_longitude"), "stores", ["longitude"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_stores_longitude"), table_name="stores")
    op.drop_index(op.f("ix_stores_latitude"), table_name="stores")
    op.drop_index(op.f("ix_stores_zip_code"), table_name="stores")
    op.drop_index(op.f("ix_stores_state"), table_name="stores")
    op.drop_index(op.f("ix_stores_city"), table_name="stores")
    op.drop_index(op.f("ix_stores_name"), table_name="stores")
    op.drop_index(op.f("ix_stores_id"), table_name="stores")
    op.drop_table("stores")
