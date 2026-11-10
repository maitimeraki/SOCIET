"""runs.corpus_label

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18

Plan §Task 1.4: a run is recognisable by name. `runs` carries the wizard's
client-side corpus name (nullable) so the history surfaces can show a corpus by
name with a fallback to its id. No backfill — a null label is a legitimate
state and the UI falls back to the dataset id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('corpus_label', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'corpus_label')
