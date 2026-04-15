"""merge alembic heads

Revision ID: 2c99f982e2b9
Revises: d4c1e8b9f2a1, f9d3c7a21b8e
Create Date: 2026-04-15 16:01:36.080701

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c99f982e2b9'
down_revision: Union[str, Sequence[str], None] = ('d4c1e8b9f2a1', 'f9d3c7a21b8e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
