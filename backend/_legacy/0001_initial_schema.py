"""Archived initial PostgreSQL schema that predates the current models.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Organizations ──
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), unique=True, index=True, nullable=False),
        sa.Column('plan', sa.String(length=50), server_default='Professional', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Users ──
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), index=True, nullable=False),
        sa.Column('email', sa.String(length=320), unique=True, index=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='INVITED', nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=True),
        sa.Column('auth_methods', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('mfa_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('mfa_secret', sa.String(length=64), nullable=True),
        sa.Column('pending_mfa_secret', sa.String(length=64), nullable=True),
        sa.Column('session_version', sa.Integer(), server_default='0', nullable=False),
        sa.Column('picture', sa.Text(), nullable=True),
        sa.Column('is_platform_admin', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_ops_only', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Invitations ──
    op.create_table(
        'invitations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('token', sa.String(length=64), unique=True, index=True, nullable=False),
        sa.Column('status', sa.String(length=20), server_default='PENDING', nullable=False),
        sa.Column('invited_by', sa.String(length=36), nullable=False),
        sa.Column('invited_by_name', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.String(length=50), nullable=False),
        sa.Column('accepted_at', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Login Attempts ──
    op.create_table(
        'login_attempts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('identifier', sa.String(length=320), unique=True, index=True, nullable=False),
        sa.Column('count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Password Reset Tokens ──
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('token_hash', sa.String(length=64), unique=True, index=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('used', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Groups ──
    op.create_table(
        'groups',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), index=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Memberships ──
    op.create_table(
        'memberships',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('group_id', sa.String(length=36), sa.ForeignKey('groups.id'), index=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), index=True, nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('ended_at', sa.String(length=50), nullable=True),
        sa.Column('ended_by', sa.String(length=36), nullable=True),
        sa.Column('end_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Candidates ──
    op.create_table(
        'candidates',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), index=True, nullable=False),
        sa.Column('first_name', sa.String(length=255), nullable=False),
        sa.Column('last_name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('email_norm', sa.String(length=320), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('phone_norm', sa.String(length=20), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('primary_skill', sa.String(length=100), nullable=True),
        sa.Column('skills', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('experience_years', sa.Float(), nullable=True),
        sa.Column('visa_status', sa.String(length=50), nullable=True),
        sa.Column('work_authorization', sa.String(length=50), nullable=True),
        sa.Column('availability_date', sa.String(length=20), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('linkedin_url', sa.Text(), nullable=True),
        sa.Column('pay_rate', sa.Float(), nullable=True),
        sa.Column('bill_rate', sa.Float(), nullable=True),
        sa.Column('target_rate', sa.Float(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('relocation', sa.Boolean(), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='NEW', nullable=False),
        sa.Column('prior_status', sa.String(length=20), nullable=True),
        sa.Column('current_group_id', sa.String(length=36), sa.ForeignKey('groups.id'), nullable=True),
        sa.Column('owner_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('updated_by', sa.String(length=36), nullable=True),
        sa.Column('bench_since', sa.String(length=50), nullable=True),
        sa.Column('archived_at', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_candidate_org_status', 'candidates', ['organization_id', 'status'])
    op.create_index('idx_candidate_org_group', 'candidates', ['organization_id', 'current_group_id'])
    op.create_index('idx_candidate_org_email', 'candidates', ['organization_id', 'email_norm'])
    op.create_index('idx_candidate_org_phone', 'candidates', ['organization_id', 'phone_norm'])
    op.create_index('idx_candidate_org_updated', 'candidates', ['organization_id', 'updated_at'])

    # ── Candidate Group Assignments (with partial unique index) ──
    op.create_table(
        'candidate_group_assignments',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), index=True, nullable=False),
        sa.Column('group_id', sa.String(length=36), sa.ForeignKey('groups.id'), nullable=False),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('started_at', sa.String(length=50), nullable=False),
        sa.Column('started_by', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('ended_at', sa.String(length=50), nullable=True),
        sa.Column('ended_by', sa.String(length=36), nullable=True),
        sa.Column('end_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'idx_one_active_group',
        'candidate_group_assignments',
        ['candidate_id'],
        unique=True,
        postgresql_where=sa.text('active = true'),
    )

    # ── Pipeline Tables ──
    op.create_table(
        'vendors',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), index=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('contact_name', sa.String(length=255), nullable=True),
        sa.Column('contact_email', sa.String(length=320), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('tier', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'clients',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), index=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('contact_name', sa.String(length=255), nullable=True),
        sa.Column('contact_email', sa.String(length=320), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), index=True, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('client_id', sa.String(length=36), sa.ForeignKey('clients.id'), nullable=True),
        sa.Column('vendor_id', sa.String(length=36), sa.ForeignKey('vendors.id'), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('work_mode', sa.String(length=20), nullable=True),
        sa.Column('rate', sa.Float(), nullable=True),
        sa.Column('skills', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('openings', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='OPEN', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'submissions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), index=True, nullable=False),
        sa.Column('job_id', sa.String(length=36), sa.ForeignKey('jobs.id'), nullable=False),
        sa.Column('client_id', sa.String(length=36), sa.ForeignKey('clients.id'), nullable=True),
        sa.Column('vendor_id', sa.String(length=36), sa.ForeignKey('vendors.id'), nullable=True),
        sa.Column('group_id', sa.String(length=36), sa.ForeignKey('groups.id'), nullable=True),
        sa.Column('submission_rate', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='SUBMITTED', nullable=False),
        sa.Column('status_history', postgresql.JSON(), nullable=True),
        sa.Column('submitted_by', sa.String(length=36), nullable=True),
        sa.Column('submitted_by_name', sa.String(length=255), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'interviews',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), index=True, nullable=False),
        sa.Column('submission_id', sa.String(length=36), sa.ForeignKey('submissions.id'), nullable=False),
        sa.Column('job_id', sa.String(length=36), sa.ForeignKey('jobs.id'), nullable=False),
        sa.Column('group_id', sa.String(length=36), sa.ForeignKey('groups.id'), nullable=True),
        sa.Column('scheduled_at', sa.String(length=50), nullable=False),
        sa.Column('timezone', sa.String(length=50), server_default='America/New_York', nullable=False),
        sa.Column('duration_minutes', sa.Integer(), server_default='60', nullable=False),
        sa.Column('mode', sa.String(length=20), server_default='VIDEO', nullable=False),
        sa.Column('round', sa.String(length=50), server_default='Round 1', nullable=False),
        sa.Column('interviewer', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='SCHEDULED', nullable=False),
        sa.Column('reschedule_history', postgresql.JSON(), nullable=True),
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'offers',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), index=True, nullable=False),
        sa.Column('submission_id', sa.String(length=36), sa.ForeignKey('submissions.id'), nullable=False),
        sa.Column('job_id', sa.String(length=36), sa.ForeignKey('jobs.id'), nullable=False),
        sa.Column('group_id', sa.String(length=36), sa.ForeignKey('groups.id'), nullable=True),
        sa.Column('bill_rate', sa.Float(), nullable=True),
        sa.Column('pay_rate', sa.Float(), nullable=True),
        sa.Column('start_date', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='EXTENDED', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'placements',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), index=True, nullable=False),
        sa.Column('offer_id', sa.String(length=36), sa.ForeignKey('offers.id'), nullable=False),
        sa.Column('job_id', sa.String(length=36), sa.ForeignKey('jobs.id'), nullable=False),
        sa.Column('group_id', sa.String(length=36), sa.ForeignKey('groups.id'), nullable=True),
        sa.Column('bill_rate', sa.Float(), nullable=True),
        sa.Column('pay_rate', sa.Float(), nullable=True),
        sa.Column('start_date', sa.String(length=20), nullable=False),
        sa.Column('end_date', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False),
        sa.Column('ended_at', sa.String(length=50), nullable=True),
        sa.Column('end_reason', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Audit, Timeline, and Operations ──
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('actor_name', sa.String(length=255), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.String(length=36), index=True, nullable=False),
        sa.Column('candidate_id', sa.String(length=36), nullable=True),
        sa.Column('before', postgresql.JSON(), nullable=True),
        sa.Column('after', postgresql.JSON(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_audit_org_created', 'audit_logs', ['organization_id', 'created_at'])

    op.create_table(
        'timeline_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), index=True, nullable=False),
        sa.Column('event', sa.String(length=100), nullable=False),
        sa.Column('detail', sa.Text(), nullable=False),
        sa.Column('meta', postgresql.JSON(), nullable=True),
        sa.Column('actor_id', sa.String(length=36), nullable=True),
        sa.Column('actor_name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), index=True, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('link', sa.Text(), nullable=True),
        sa.Column('read', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'email_outbox',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('to', sa.String(length=320), nullable=False),
        sa.Column('subject', sa.String(length=500), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='PENDING', index=True, nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('sent_at', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'notes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), index=True, nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('visibility', sa.String(length=20), server_default='STANDARD', nullable=False),
        sa.Column('author_id', sa.String(length=36), nullable=False),
        sa.Column('author_name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'tasks',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('assignee_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('due_date', sa.String(length=20), nullable=True),
        sa.Column('priority', sa.String(length=20), server_default='MEDIUM', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='OPEN', nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('candidate_id', sa.String(length=36), sa.ForeignKey('candidates.id'), index=True, nullable=False),
        sa.Column('doc_type', sa.String(length=50), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(length=500), nullable=False),
        sa.Column('scan_status', sa.String(length=20), server_default='PENDING', nullable=False),
        sa.Column('scan_engine', sa.String(length=50), server_default='heuristic', nullable=False),
        sa.Column('scan_reason', sa.String(length=255), nullable=True),
        sa.Column('scanned_at', sa.String(length=50), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('uploaded_by', sa.String(length=36), nullable=False),
        sa.Column('uploaded_by_name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'background_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='PENDING', nullable=False),
        sa.Column('payload', postgresql.JSON(), nullable=True),
        sa.Column('result', postgresql.JSON(), nullable=True),
        sa.Column('result_csv', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.String(length=50), nullable=True),
        sa.Column('finished_at', sa.String(length=50), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_by_name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'saved_views',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('page', sa.String(length=50), nullable=False),
        sa.Column('filters', postgresql.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'settings',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), unique=True, nullable=False),
        sa.Column('bench_aging_warning_days', sa.Integer(), server_default='15', nullable=False),
        sa.Column('bench_aging_critical_days', sa.Integer(), server_default='30', nullable=False),
        sa.Column('weekly_submission_target', sa.Integer(), server_default='5', nullable=False),
        sa.Column('interview_default_timezone', sa.String(length=50), server_default='America/New_York', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('settings')
    op.drop_table('saved_views')
    op.drop_table('background_jobs')
    op.drop_table('documents')
    op.drop_table('notes')
    op.drop_table('tasks')
    op.drop_table('email_outbox')
    op.drop_table('notifications')
    op.drop_table('timeline_events')
    op.drop_table('audit_logs')
    op.drop_table('placements')
    op.drop_table('offers')
    op.drop_table('interviews')
    op.drop_table('submissions')
    op.drop_table('jobs')
    op.drop_table('clients')
    op.drop_table('vendors')
    op.drop_table('candidate_group_assignments')
    op.drop_table('candidates')
    op.drop_table('memberships')
    op.drop_table('groups')
    op.drop_table('password_reset_tokens')
    op.drop_table('login_attempts')
    op.drop_table('invitations')
    op.drop_table('users')
    op.drop_table('organizations')

