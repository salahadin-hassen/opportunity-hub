"""add conditional request validators, source test results and refresh checks

Revision ID: 15603fdb3a61
Revises: 4bc3f2f0619d
Create Date: 2026-11-15 07:05:13.627097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '15603fdb3a61'
down_revision: Union[str, Sequence[str], None] = '4bc3f2f0619d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Additive: one new table and nullable columns; no existing row is rewritten."""
    # Runs gain a third kind (a refresh of published opportunities). Not detected by autogenerate.
    op.drop_constraint('ck_ingestion_runs_kind', 'ingestion_runs', type_='check')
    op.create_check_constraint('ck_ingestion_runs_kind', 'ingestion_runs', "kind IN ('discover', 'process', 'refresh')")
    op.create_table('opportunity_refresh_checks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('acquisition_source_id', sa.Uuid(), nullable=True),
    sa.Column('url', sa.String(length=2000), nullable=False),
    sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('outcome', sa.String(length=24), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('content_changed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('etag', sa.String(length=512), nullable=True),
    sa.Column('last_modified', sa.String(length=512), nullable=True),
    sa.Column('page_text', sa.Text(), nullable=True),
    sa.Column('extraction', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('findings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('review_state', sa.String(length=16), nullable=False),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_notes', sa.Text(), nullable=True),
    sa.Column('candidate_id', sa.Uuid(), nullable=True),
    sa.CheckConstraint("outcome IN ('unchanged', 'material_update', 'deadline_changed', 'closed', 'new_cycle', 'source_unavailable', 'review_required')", name='ck_opportunity_refresh_checks_outcome'),
    sa.CheckConstraint("review_state IN ('none', 'pending', 'acknowledged', 'dismissed')", name='ck_opportunity_refresh_checks_review_state'),
    sa.CheckConstraint('consecutive_failures >= 0', name='ck_opportunity_refresh_checks_failures_nonnegative'),
    sa.ForeignKeyConstraint(['acquisition_source_id'], ['acquisition_sources.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['candidate_id'], ['ingestion_candidates.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_opportunity_refresh_checks_opportunity', 'opportunity_refresh_checks', ['opportunity_id', 'checked_at'], unique=False)
    op.create_index('ix_opportunity_refresh_checks_review_state', 'opportunity_refresh_checks', ['review_state'], unique=False)
    op.add_column('acquisition_sources', sa.Column('last_test_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('acquisition_sources', sa.Column('last_test_passed', sa.Boolean(), nullable=True))
    op.add_column('acquisition_sources', sa.Column('last_test_report', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('ingestion_candidates', sa.Column('etag', sa.String(length=512), nullable=True))
    op.add_column('ingestion_candidates', sa.Column('last_modified', sa.String(length=512), nullable=True))
    op.add_column('ingestion_candidates', sa.Column('resume_state', sa.String(length=24), nullable=True))


def downgrade() -> None:
    """Downgrade schema. Refresh runs are deleted so the narrower check on ``kind`` holds again."""
    op.drop_column('ingestion_candidates', 'resume_state')
    op.drop_column('ingestion_candidates', 'last_modified')
    op.drop_column('ingestion_candidates', 'etag')
    op.drop_column('acquisition_sources', 'last_test_report')
    op.drop_column('acquisition_sources', 'last_test_passed')
    op.drop_column('acquisition_sources', 'last_test_at')
    op.drop_index('ix_opportunity_refresh_checks_review_state', table_name='opportunity_refresh_checks')
    op.drop_index('ix_opportunity_refresh_checks_opportunity', table_name='opportunity_refresh_checks')
    op.drop_table('opportunity_refresh_checks')
    op.execute("DELETE FROM ingestion_runs WHERE kind = 'refresh'")
    op.drop_constraint('ck_ingestion_runs_kind', 'ingestion_runs', type_='check')
    op.create_check_constraint('ck_ingestion_runs_kind', 'ingestion_runs', "kind IN ('discover', 'process')")
