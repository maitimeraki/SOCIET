"""uploads.name

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18

An upload's name is metadata, not part of its storage address. `object_key` is
`<user_id>/<upload_id>` (the address), so the filename has to be stored
separately — this column holds it. Nullable add, no backfill: rows written
before this column exists are null and the documents list reads name as-is.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('uploads', sa.Column('name', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('uploads', 'name')
