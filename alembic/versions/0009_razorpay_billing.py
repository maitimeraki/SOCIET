"""razorpay billing: subscriptions mirror Razorpay ids, currency and tax

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18

Razorpay replaces Stripe as the payment provider. upgrade() refuses to run while
subscriptions holds rows, so cancel and delete any Stripe-era rows first. It
then renames the provider id columns to razorpay_*, drops stripe_customer_id,
and adds nullable currency and billing_country plus tax_amount (default 0).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Renaming in place would carry Stripe ids into Razorpay columns. Refuse rather
    # than guess: cancel any Stripe subscriptions and clear the rows first.
    # Offline mode cannot inspect rows, so this guard is skipped and the operator must confirm subscriptions is empty.
    if not context.is_offline_mode():
        existing = op.get_bind().execute(sa.text('SELECT count(*) FROM subscriptions')).scalar()
        if existing:
            raise RuntimeError(
                f'subscriptions holds {existing} Stripe-era row(s); cancel them and delete '
                'the rows before running migration 0009'
            )
    op.drop_index('ix_subscriptions_stripe_customer_id', table_name='subscriptions')
    op.drop_column('subscriptions', 'stripe_customer_id')
    op.alter_column(
        'subscriptions', 'stripe_subscription_id', new_column_name='razorpay_subscription_id'
    )
    op.alter_column('subscriptions', 'price_id', new_column_name='razorpay_plan_id')
    op.add_column('subscriptions', sa.Column('currency', sa.Text(), nullable=True))
    op.add_column('subscriptions', sa.Column('billing_country', sa.Text(), nullable=True))
    op.add_column(
        'subscriptions',
        sa.Column('tax_amount', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('subscriptions', 'tax_amount')
    op.drop_column('subscriptions', 'billing_country')
    op.drop_column('subscriptions', 'currency')
    op.alter_column(
        'subscriptions', 'razorpay_plan_id', new_column_name='price_id'
    )
    op.alter_column(
        'subscriptions', 'razorpay_subscription_id', new_column_name='stripe_subscription_id'
    )
    # Razorpay rows have no Stripe customer; the restored column fills them with ''.
    op.add_column(
        'subscriptions',
        sa.Column('stripe_customer_id', sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.alter_column('subscriptions', 'stripe_customer_id', server_default=None)
    op.create_index(
        'ix_subscriptions_stripe_customer_id',
        'subscriptions',
        ['stripe_customer_id'],
        unique=False,
    )
