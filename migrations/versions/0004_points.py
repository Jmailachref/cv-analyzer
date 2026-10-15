"""points: recruiters give -100 to 100 points to a passage, never 0

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_highlights_points', 'highlights', type_='check')
    op.create_check_constraint('ck_highlights_points', 'highlights', 'points BETWEEN -100 AND 100 AND points <> 0')
    # Grids no longer carry score settings (cap, weights): the score is a plain sum of points.
    op.execute("UPDATE grids SET settings = '{}'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM highlights WHERE points < 1")
    op.execute("UPDATE highlights SET points = 20 WHERE points > 20")
    op.drop_constraint('ck_highlights_points', 'highlights', type_='check')
    op.create_check_constraint('ck_highlights_points', 'highlights', 'points BETWEEN 1 AND 20')
