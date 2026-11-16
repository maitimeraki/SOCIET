"""verdict retry: at most one in-flight verdict job per run

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-16

A unique partial index on jobs(run_id) over the in-flight verdict jobs. A double submit of
POST /debates/{run_id}/verdict/retry then cannot enqueue a second job: the second insert is
refused by the database, whichever request got there first.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'jobs_one_verdict_retry_in_flight',
        'jobs',
        ['run_id'],
        unique=True,
        postgresql_where=sa.text("kind = 'verdict' AND status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index('jobs_one_verdict_retry_in_flight', table_name='jobs')
