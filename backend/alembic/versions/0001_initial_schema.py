"""Initial schema: projects, plans, supply chain, risk, runs and audit trail

Revision ID: 0001_initial
Revises: 
Create Date: 2026-10-21 18:38:53.372443
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ai_provider_configs',
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('base_url', sa.String(length=400), nullable=True),
    sa.Column('model', sa.String(length=200), nullable=True),
    sa.Column('api_key_encrypted', sa.Text(), nullable=True),
    sa.Column('timeout_seconds', sa.Float(), nullable=False),
    sa.Column('max_retries', sa.Integer(), nullable=False),
    sa.Column('monthly_budget_usd', sa.Float(), nullable=False),
    sa.Column('input_price_per_mtok', sa.Float(), nullable=False),
    sa.Column('output_price_per_mtok', sa.Float(), nullable=False),
    sa.Column('extra', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_provider_configs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_provider_configs_provider'), ['provider'], unique=True)

    op.create_table('audit_logs',
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('actor', sa.String(length=200), nullable=False),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=60), nullable=False),
    sa.Column('entity_id', sa.String(length=36), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_logs_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_project_id'), ['project_id'], unique=False)

    op.create_table('calibration_records',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('milestone', sa.String(length=200), nullable=False),
    sa.Column('forecast_probability', sa.Float(), nullable=False),
    sa.Column('outcome', sa.Boolean(), nullable=False),
    sa.Column('forecast_date', sa.Date(), nullable=True),
    sa.Column('outcome_date', sa.Date(), nullable=True),
    sa.Column('source', sa.String(length=80), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('calibration_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calibration_records_project_id'), ['project_id'], unique=False)

    op.create_table('jobs',
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('kind', sa.String(length=60), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('progress', sa.Float(), nullable=False),
    sa.Column('message', sa.String(length=400), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('cancel_requested', sa.Boolean(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('idempotency_key', sa.String(length=120), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_jobs_idempotency_key'), ['idempotency_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_status'), ['status'], unique=False)

    op.create_table('projects',
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('product', sa.String(length=200), nullable=False),
    sa.Column('version', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('launch_deadline', sa.Date(), nullable=True),
    sa.Column('baseline_launch_date', sa.Date(), nullable=True),
    sa.Column('working_days_per_week', sa.Integer(), nullable=False),
    sa.Column('holidays', sa.JSON(), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('delay_cost_per_day', sa.Float(), nullable=False),
    sa.Column('intervention_budget', sa.Float(), nullable=False),
    sa.Column('yield_start', sa.Float(), nullable=False),
    sa.Column('yield_target', sa.Float(), nullable=False),
    sa.Column('ramp_days', sa.Integer(), nullable=False),
    sa.Column('unit_margin', sa.Float(), nullable=False),
    sa.Column('planned_volume', sa.Integer(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('owner', sa.String(length=200), nullable=False),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_projects_key'), ['key'], unique=True)
        batch_op.create_index(batch_op.f('ix_projects_status'), ['status'], unique=False)

    op.create_table('users',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('roles', sa.JSON(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('ai_conversations',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_conversations_project_id'), ['project_id'], unique=False)

    op.create_table('ecos',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('probability', sa.Float(), nullable=False),
    sa.Column('rework_days', sa.Float(), nullable=False),
    sa.Column('impact_task_ids', sa.JSON(), nullable=False),
    sa.Column('cost', sa.Float(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ecos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ecos_project_id'), ['project_id'], unique=False)

    op.create_table('optimization_runs',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('baseline_simulation_id', sa.String(length=36), nullable=True),
    sa.Column('objective', sa.String(length=60), nullable=False),
    sa.Column('budget', sa.Float(), nullable=False),
    sa.Column('weights', sa.JSON(), nullable=False),
    sa.Column('constraints', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('results', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('optimization_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_optimization_runs_project_id'), ['project_id'], unique=False)

    op.create_table('project_members',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=40), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('project_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_project_members_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_project_members_user_id'), ['user_id'], unique=False)

    op.create_table('resources',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('capacity', sa.Float(), nullable=False),
    sa.Column('availability', sa.Float(), nullable=False),
    sa.Column('cost_per_day', sa.Float(), nullable=False),
    sa.Column('overtime_available', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_resources_project_id'), ['project_id'], unique=False)

    op.create_table('risks',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=False),
    sa.Column('target_type', sa.String(length=30), nullable=False),
    sa.Column('target_id', sa.String(length=36), nullable=True),
    sa.Column('probability', sa.Float(), nullable=False),
    sa.Column('impact_days', sa.Float(), nullable=False),
    sa.Column('impact_cost', sa.Float(), nullable=False),
    sa.Column('distribution', sa.String(length=30), nullable=False),
    sa.Column('correlation_group', sa.String(length=80), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('owner', sa.String(length=120), nullable=False),
    sa.Column('evidence', sa.Text(), nullable=False),
    sa.Column('metadata_json', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('risks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_risks_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_risks_target_id'), ['target_id'], unique=False)

    op.create_table('scenarios',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('is_baseline', sa.Boolean(), nullable=False),
    sa.Column('parent_id', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('approved_by', sa.String(length=200), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['scenarios.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_scenarios_project_id'), ['project_id'], unique=False)

    op.create_table('simulation_snapshots',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('simulation_id', sa.String(length=36), nullable=False),
    sa.Column('scenario_id', sa.String(length=36), nullable=True),
    sa.Column('label', sa.String(length=300), nullable=False),
    sa.Column('p50_days', sa.Float(), nullable=False),
    sa.Column('p90_days', sa.Float(), nullable=False),
    sa.Column('on_time_probability', sa.Float(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('simulation_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_simulation_snapshots_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulation_snapshots_simulation_id'), ['simulation_id'], unique=False)

    op.create_table('suppliers',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('region', sa.String(length=80), nullable=False),
    sa.Column('reliability', sa.Float(), nullable=False),
    sa.Column('lead_time_days', sa.Float(), nullable=False),
    sa.Column('lead_time_cv', sa.Float(), nullable=False),
    sa.Column('disruption_prob', sa.Float(), nullable=False),
    sa.Column('disruption_delay_days', sa.Float(), nullable=False),
    sa.Column('cost_factor', sa.Float(), nullable=False),
    sa.Column('qualification_required', sa.Boolean(), nullable=False),
    sa.Column('qualified', sa.Boolean(), nullable=False),
    sa.Column('dual_source', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'name', name='uq_supplier_project_name')
    )
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_suppliers_project_id'), ['project_id'], unique=False)

    op.create_table('tasks',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('phase', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('wbs', sa.String(length=40), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('duration_days', sa.Float(), nullable=False),
    sa.Column('distribution', sa.String(length=20), nullable=False),
    sa.Column('duration_min', sa.Float(), nullable=True),
    sa.Column('duration_mode', sa.Float(), nullable=True),
    sa.Column('duration_max', sa.Float(), nullable=True),
    sa.Column('std_dev', sa.Float(), nullable=True),
    sa.Column('buffer_days', sa.Float(), nullable=False),
    sa.Column('risk_factor', sa.Float(), nullable=False),
    sa.Column('cost', sa.Float(), nullable=False),
    sa.Column('is_gate', sa.Boolean(), nullable=False),
    sa.Column('optional', sa.Boolean(), nullable=False),
    sa.Column('is_milestone', sa.Boolean(), nullable=False),
    sa.Column('fixed_start_offset', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'code', name='uq_task_project_code')
    )
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tasks_phase'), ['phase'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_project_id'), ['project_id'], unique=False)

    op.create_table('actual_events',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('task_id', sa.String(length=36), nullable=True),
    sa.Column('supplier_id', sa.String(length=36), nullable=True),
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('observed_delay_days', sa.Float(), nullable=False),
    sa.Column('observed_cost', sa.Float(), nullable=False),
    sa.Column('occurred_on', sa.Date(), nullable=True),
    sa.Column('evidence', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=120), nullable=False),
    sa.Column('metadata_json', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('actual_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_actual_events_project_id'), ['project_id'], unique=False)

    op.create_table('ai_messages',
    sa.Column('conversation_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('citations', sa.JSON(), nullable=False),
    sa.Column('tool_calls', sa.JSON(), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_messages_conversation_id'), ['conversation_id'], unique=False)

    op.create_table('components',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('part_number', sa.String(length=80), nullable=False),
    sa.Column('supplier_id', sa.String(length=36), nullable=True),
    sa.Column('alternative_supplier_id', sa.String(length=36), nullable=True),
    sa.Column('unit_cost', sa.Float(), nullable=False),
    sa.Column('qty_per_unit', sa.Float(), nullable=False),
    sa.Column('lead_time_days', sa.Float(), nullable=False),
    sa.Column('safety_stock_days', sa.Float(), nullable=False),
    sa.Column('inventory_days', sa.Float(), nullable=False),
    sa.Column('criticality', sa.Float(), nullable=False),
    sa.Column('single_source', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['alternative_supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'part_number', name='uq_component_project_pn')
    )
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_components_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_components_supplier_id'), ['supplier_id'], unique=False)

    op.create_table('dependencies',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('from_task_id', sa.String(length=36), nullable=False),
    sa.Column('to_task_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=2), nullable=False),
    sa.Column('lag_days', sa.Float(), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['from_task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['to_task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('from_task_id', 'to_task_id', name='uq_dependency_pair')
    )
    with op.batch_alter_table('dependencies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dependencies_from_task_id'), ['from_task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dependencies_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dependencies_to_task_id'), ['to_task_id'], unique=False)

    op.create_table('interventions',
    sa.Column('scenario_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=60), nullable=False),
    sa.Column('target_type', sa.String(length=30), nullable=False),
    sa.Column('target_id', sa.String(length=36), nullable=True),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('cost', sa.Float(), nullable=False),
    sa.Column('label', sa.String(length=300), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('interventions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_interventions_scenario_id'), ['scenario_id'], unique=False)

    op.create_table('milestones',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('task_id', sa.String(length=36), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('customer_commitment', sa.Boolean(), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('milestones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_milestones_project_id'), ['project_id'], unique=False)

    op.create_table('mitigation_plans',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('risk_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('cost', sa.Float(), nullable=False),
    sa.Column('expected_benefit_days', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['risk_id'], ['risks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mitigation_plans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mitigation_plans_project_id'), ['project_id'], unique=False)

    op.create_table('simulation_runs',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('scenario_id', sa.String(length=36), nullable=True),
    sa.Column('job_id', sa.String(length=36), nullable=True),
    sa.Column('label', sa.String(length=300), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('iterations', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('engine_version', sa.String(length=30), nullable=False),
    sa.Column('model_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.Column('samples', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('simulation_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_simulation_runs_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulation_runs_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulation_runs_scenario_id'), ['scenario_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulation_runs_status'), ['status'], unique=False)

    op.create_table('task_resources',
    sa.Column('task_id', sa.String(length=36), nullable=False),
    sa.Column('resource_id', sa.String(length=36), nullable=False),
    sa.Column('demand', sa.Float(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['resource_id'], ['resources.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id', 'resource_id', name='uq_task_resource')
    )
    with op.batch_alter_table('task_resources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_resources_resource_id'), ['resource_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_resources_task_id'), ['task_id'], unique=False)

    op.create_table('validation_tests',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('task_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('test_type', sa.String(length=40), nullable=False),
    sa.Column('required_passes', sa.Integer(), nullable=False),
    sa.Column('failure_probability', sa.Float(), nullable=False),
    sa.Column('retest_days', sa.Float(), nullable=False),
    sa.Column('is_gate', sa.Boolean(), nullable=False),
    sa.Column('correlation_group', sa.String(length=80), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('validation_tests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_validation_tests_project_id'), ['project_id'], unique=False)

    op.create_table('inventories',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('component_id', sa.String(length=36), nullable=False),
    sa.Column('on_hand_qty', sa.Float(), nullable=False),
    sa.Column('safety_stock_qty', sa.Float(), nullable=False),
    sa.Column('location', sa.String(length=120), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('inventories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inventories_project_id'), ['project_id'], unique=False)

    op.create_table('purchase_orders',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('component_id', sa.String(length=36), nullable=False),
    sa.Column('supplier_id', sa.String(length=36), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('unit_cost', sa.Float(), nullable=False),
    sa.Column('ordered_offset', sa.Float(), nullable=False),
    sa.Column('expected_offset', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('expedite_cost', sa.Float(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchase_orders_project_id'), ['project_id'], unique=False)

    op.create_table('quotes',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('supplier_id', sa.String(length=36), nullable=False),
    sa.Column('component_id', sa.String(length=36), nullable=False),
    sa.Column('unit_cost', sa.Float(), nullable=False),
    sa.Column('lead_time_days', sa.Float(), nullable=False),
    sa.Column('moq', sa.Integer(), nullable=False),
    sa.Column('qualified', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.String(length=400), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('quotes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_quotes_project_id'), ['project_id'], unique=False)

    op.create_table('task_components',
    sa.Column('task_id', sa.String(length=36), nullable=False),
    sa.Column('component_id', sa.String(length=36), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('required_by_offset', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id', 'component_id', name='uq_task_component')
    )
    with op.batch_alter_table('task_components', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_components_component_id'), ['component_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_components_task_id'), ['task_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('task_components', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_components_task_id'))
        batch_op.drop_index(batch_op.f('ix_task_components_component_id'))

    op.drop_table('task_components')
    with op.batch_alter_table('quotes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_quotes_project_id'))

    op.drop_table('quotes')
    with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_purchase_orders_project_id'))

    op.drop_table('purchase_orders')
    with op.batch_alter_table('inventories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inventories_project_id'))

    op.drop_table('inventories')
    with op.batch_alter_table('validation_tests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_validation_tests_project_id'))

    op.drop_table('validation_tests')
    with op.batch_alter_table('task_resources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_resources_task_id'))
        batch_op.drop_index(batch_op.f('ix_task_resources_resource_id'))

    op.drop_table('task_resources')
    with op.batch_alter_table('simulation_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_simulation_runs_status'))
        batch_op.drop_index(batch_op.f('ix_simulation_runs_scenario_id'))
        batch_op.drop_index(batch_op.f('ix_simulation_runs_project_id'))
        batch_op.drop_index(batch_op.f('ix_simulation_runs_job_id'))

    op.drop_table('simulation_runs')
    with op.batch_alter_table('mitigation_plans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mitigation_plans_project_id'))

    op.drop_table('mitigation_plans')
    with op.batch_alter_table('milestones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_milestones_project_id'))

    op.drop_table('milestones')
    with op.batch_alter_table('interventions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_interventions_scenario_id'))

    op.drop_table('interventions')
    with op.batch_alter_table('dependencies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dependencies_to_task_id'))
        batch_op.drop_index(batch_op.f('ix_dependencies_project_id'))
        batch_op.drop_index(batch_op.f('ix_dependencies_from_task_id'))

    op.drop_table('dependencies')
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_components_supplier_id'))
        batch_op.drop_index(batch_op.f('ix_components_project_id'))

    op.drop_table('components')
    with op.batch_alter_table('ai_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_messages_conversation_id'))

    op.drop_table('ai_messages')
    with op.batch_alter_table('actual_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_actual_events_project_id'))

    op.drop_table('actual_events')
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tasks_project_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_phase'))

    op.drop_table('tasks')
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_suppliers_project_id'))

    op.drop_table('suppliers')
    with op.batch_alter_table('simulation_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_simulation_snapshots_simulation_id'))
        batch_op.drop_index(batch_op.f('ix_simulation_snapshots_project_id'))

    op.drop_table('simulation_snapshots')
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_scenarios_project_id'))

    op.drop_table('scenarios')
    with op.batch_alter_table('risks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_risks_target_id'))
        batch_op.drop_index(batch_op.f('ix_risks_project_id'))

    op.drop_table('risks')
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_resources_project_id'))

    op.drop_table('resources')
    with op.batch_alter_table('project_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_project_members_user_id'))
        batch_op.drop_index(batch_op.f('ix_project_members_project_id'))

    op.drop_table('project_members')
    with op.batch_alter_table('optimization_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_optimization_runs_project_id'))

    op.drop_table('optimization_runs')
    with op.batch_alter_table('ecos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ecos_project_id'))

    op.drop_table('ecos')
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_conversations_project_id'))

    op.drop_table('ai_conversations')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_projects_status'))
        batch_op.drop_index(batch_op.f('ix_projects_key'))

    op.drop_table('projects')
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_status'))
        batch_op.drop_index(batch_op.f('ix_jobs_project_id'))
        batch_op.drop_index(batch_op.f('ix_jobs_kind'))
        batch_op.drop_index(batch_op.f('ix_jobs_idempotency_key'))

    op.drop_table('jobs')
    with op.batch_alter_table('calibration_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calibration_records_project_id'))

    op.drop_table('calibration_records')
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_logs_project_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_action'))

    op.drop_table('audit_logs')
    with op.batch_alter_table('ai_provider_configs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_provider_configs_provider'))

    op.drop_table('ai_provider_configs')
