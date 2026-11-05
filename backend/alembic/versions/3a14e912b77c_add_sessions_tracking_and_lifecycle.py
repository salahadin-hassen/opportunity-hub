"""add sessions, email outbox, tracking, and account lifecycle

Revision ID: 3a14e912b77c
Revises: 2d0318b24522
Create Date: 2026-11-05 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3a14e912b77c'
down_revision: Union[str, Sequence[str], None] = '2d0318b24522'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. User lifecycle columns
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('deletion_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('deletion_due_at', sa.DateTime(timezone=True), nullable=True))

    # 2. Sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('client_ip', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sessions_token_hash', 'sessions', ['token_hash'], unique=True)
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'], unique=False)
    op.create_index('ix_sessions_active', 'sessions', ['user_id', 'expires_at', 'revoked_at'], unique=False)

    # 3. Email tokens
    op.create_table(
        'email_tokens',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('purpose', sa.String(length=32), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_tokens_token_hash', 'email_tokens', ['token_hash'], unique=True)
    op.create_index('ix_email_tokens_user_id', 'email_tokens', ['user_id'], unique=False)
    op.create_index('ix_email_tokens_lookup', 'email_tokens', ['purpose', 'token_hash'], unique=False)

    # 4. Email outbox
    op.create_table(
        'email_outbox',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('to_address', sa.String(length=320), nullable=False),
        sa.Column('template', sa.String(length=64), nullable=False),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('send_after', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dedupe_key', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dedupe_key'),
    )
    op.create_index('ix_email_outbox_due', 'email_outbox', ['status', 'send_after'], unique=False)

    # 5. Deletion tombstones
    op.create_table(
        'deletion_tombstones',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('purged_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
    )

    # 6. Saved opportunities
    op.create_table(
        'saved_opportunities',
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('opportunity_id', sa.Uuid(), nullable=False),
        sa.Column('confirmations', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('reminders_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('profile_id', 'opportunity_id'),
    )
    op.create_index('ix_saved_opportunities_profile_created', 'saved_opportunities', ['profile_id', 'created_at'], unique=False)

    # 7. Applications
    op.create_table(
        'applications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('opportunity_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='draft', nullable=False),
        sa.Column('outcome', sa.String(length=32), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', 'opportunity_id', name='uq_applications_profile_opportunity'),
    )
    op.create_index('ix_applications_profile_status', 'applications', ['profile_id', 'status'], unique=False)
    op.create_index('ix_applications_profile_id', 'applications', ['profile_id'], unique=False)
    op.create_index('ix_applications_opportunity_id', 'applications', ['opportunity_id'], unique=False)

    # 8. Application items
    op.create_table(
        'application_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('application_id', sa.Uuid(), nullable=False),
        sa.Column('requirement_id', sa.Uuid(), nullable=True),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('order_index', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_application_items_application_id', 'application_items', ['application_id'], unique=False)


def downgrade() -> None:
    op.drop_table('application_items')
    op.drop_table('applications')
    op.drop_table('saved_opportunities')
    op.drop_table('deletion_tombstones')
    op.drop_table('email_outbox')
    op.drop_table('email_tokens')
    op.drop_table('sessions')
    op.drop_column('users', 'deletion_due_at')
    op.drop_column('users', 'deletion_requested_at')
    op.drop_column('users', 'email_verified_at')

