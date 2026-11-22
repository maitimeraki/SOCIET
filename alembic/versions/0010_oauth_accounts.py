"""oauth accounts and passwordless users

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-21

Adds the `oauth_accounts` link table (GitHub/Google subject -> local user) and
makes `users.password_hash` nullable so an OAuth-only account has no local
password. The unique keys are the provider subject and one identity per
user/provider; email is informational and never the lookup key.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'users', 'password_hash', existing_type=sa.Text(), nullable=True
    )
    op.create_table(
        'oauth_accounts',
        sa.Column(
            'id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False
        ),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('provider_user_id', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('github','google')", name='ck_oauth_accounts_provider'
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'provider', 'provider_user_id', name='uq_oauth_accounts_provider_subject'
        ),
        sa.UniqueConstraint(
            'user_id', 'provider', name='uq_oauth_accounts_user_provider'
        ),
    )
    op.create_index(
        'ix_oauth_accounts_user_id', 'oauth_accounts', ['user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_oauth_accounts_user_id', table_name='oauth_accounts')
    op.drop_table('oauth_accounts')
    # An OAuth-only account cannot satisfy the restored NOT NULL. Clear the
    # password so the column can be tightened (the account can reset it later).
    op.execute("UPDATE users SET password_hash = '' WHERE password_hash IS NULL")
    op.alter_column(
        'users', 'password_hash', existing_type=sa.Text(), nullable=False
    )
