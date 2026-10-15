"""no warning words: only missing core skills cost points; highlights worth 1 to 20

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    # Grids lose their warning words, and criteria their kind.
    for grid_id, criteria in conn.execute(sa.text("SELECT id, criteria FROM grids")).all():
        if isinstance(criteria, str):
            criteria = json.loads(criteria)
        kept = [{k: v for k, v in c.items() if k != "kind"} for c in criteria if c.get("kind", "skill") != "alert"]
        conn.execute(
            sa.text("UPDATE grids SET criteria = CAST(:c AS jsonb) WHERE id = :id"), {"c": json.dumps(kept), "id": grid_id}
        )
    op.drop_column('offers', 'alerts')
    op.drop_constraint('ck_highlights_points', 'highlights', type_='check')
    op.create_check_constraint('ck_highlights_points', 'highlights', 'points BETWEEN 1 AND 20')


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE highlights SET points = 5 WHERE points > 5")
    op.drop_constraint('ck_highlights_points', 'highlights', type_='check')
    op.create_check_constraint('ck_highlights_points', 'highlights', 'points BETWEEN 1 AND 5')
    op.add_column(
        'offers',
        sa.Column(
            'alerts',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
