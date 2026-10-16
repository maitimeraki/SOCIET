"""run/job history indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14

Indexes for the queries Task 5 introduces (plan §6, §13): the keyset-paginated
debates list walks `runs` by owner newest-first on `(created_at, id) DESC`, and
`jobs` is looked up by owner. No column changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'runs_user_id_created_at_id_idx',
        'runs',
        ['user_id', sa.text('created_at DESC'), sa.text('id DESC')],
        unique=False,
    )
    op.create_index('jobs_user_id_idx', 'jobs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('jobs_user_id_idx', table_name='jobs')
    op.drop_index('runs_user_id_created_at_id_idx', table_name='runs')
