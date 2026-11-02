"""billing and compliance schema

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02

Adds the account role/plan and consent timestamps to users, the reserved-units
lease to jobs, and the billing/compliance tables: subscriptions, the usage
ledger (usage_periods, usage_events, llm_usage), Stripe webhook idempotency
(webhook_events), and legal documents plus per-user consent (legal_documents,
user_consents). `usage_events.reason` records the reason code a void carries.
All added columns have defaults, so no backfill is needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('role', sa.Text(), server_default=sa.text("'user'"), nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('plan_key', sa.Text(), server_default=sa.text("'free'"), nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('age_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        'ck_users_role', 'users', "role IN ('user','support','admin')"
    )

    op.add_column(
        'jobs',
        sa.Column('reserved_units', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    )
    op.add_column(
        'jobs',
        sa.Column('reserved_period_start', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'jobs',
        sa.Column('reserved_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'subscriptions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('stripe_customer_id', sa.Text(), nullable=False),
        sa.Column('stripe_subscription_id', sa.Text(), nullable=True),
        sa.Column('price_id', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_subscription_id'),
    )
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'], unique=False)
    op.create_index('ix_subscriptions_stripe_customer_id', 'subscriptions', ['stripe_customer_id'], unique=False)

    op.create_table(
        'usage_periods',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('units_used', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('units_reserved', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'period_start'),
        sa.CheckConstraint('units_used >= 0', name='ck_usage_periods_units_used'),
        sa.CheckConstraint('units_reserved >= 0', name='ck_usage_periods_units_reserved'),
    )

    op.create_table(
        'usage_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('kind', sa.Text(), server_default=sa.text("'units'"), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('idempotency_key', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), server_default=sa.text("'consumed'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'period_start', 'kind', 'idempotency_key', name='uq_usage_events_idempotency'),
    )
    op.create_index('usage_events_user_id_period_start_idx', 'usage_events', ['user_id', 'period_start'], unique=False)

    op.create_table(
        'llm_usage',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('run_id', sa.UUID(), nullable=True),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('call_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=True),
        sa.Column('model', sa.Text(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('cost_usd', sa.Double(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('call_id'),
    )
    op.create_index('llm_usage_user_id_created_at_idx', 'llm_usage', ['user_id', 'created_at'], unique=False)

    op.create_table(
        'webhook_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('provider_event_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('payload_hash', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_event_id'),
    )
    op.create_index('webhook_events_status_received_at_idx', 'webhook_events', ['status', 'received_at'], unique=False)

    op.create_table(
        'legal_documents',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('version', sa.Text(), nullable=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('content_sha256', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', 'version', name='uq_legal_documents_slug_version'),
    )

    op.create_table(
        'user_consents',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ip', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['legal_documents.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'document_id', name='uq_user_consents_user_document'),
    )


def downgrade() -> None:
    op.drop_table('user_consents')
    op.drop_table('legal_documents')
    op.drop_index('webhook_events_status_received_at_idx', table_name='webhook_events')
    op.drop_table('webhook_events')
    op.drop_index('llm_usage_user_id_created_at_idx', table_name='llm_usage')
    op.drop_table('llm_usage')
    op.drop_index('usage_events_user_id_period_start_idx', table_name='usage_events')
    op.drop_table('usage_events')
    op.drop_table('usage_periods')
    op.drop_index('ix_subscriptions_stripe_customer_id', table_name='subscriptions')
    op.drop_index('ix_subscriptions_user_id', table_name='subscriptions')
    op.drop_table('subscriptions')

    op.drop_column('jobs', 'reserved_at')
    op.drop_column('jobs', 'reserved_period_start')
    op.drop_column('jobs', 'reserved_units')

    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.drop_column('users', 'age_confirmed_at')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'plan_key')
    op.drop_column('users', 'role')
