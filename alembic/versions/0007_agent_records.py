"""agent records: one backend-only record per candidate per run

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-15

Adds agent_records: one row per candidate of a run, holding the AgentRecord JSON
(backend-only; the client sees AgentView alone). `seat` is the final seat index of
a seated candidate, so the roster can read seat order without parsing JSON. The
(run_id, node_id) unique key makes a repeated write insert nothing new. Rows are
removed by the runs FK cascade on run or account deletion.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('node_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('seat', sa.Integer(), nullable=True),
        sa.Column('record', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('published','rejected','stale')", name='ck_agent_records_status'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'node_id', name='uq_agent_records_run_id_node_id'),
    )


def downgrade() -> None:
    op.drop_table('agent_records')
