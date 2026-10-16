"""uploads.extracted_text

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14

Plan §7: the worker writes the extracted document text next to the object
metadata, so `uploads` carries `extracted_text` (nullable until the extract
job runs).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('uploads', sa.Column('extracted_text', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('uploads', 'extracted_text')
