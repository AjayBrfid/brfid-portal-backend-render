"""add support ticketing tables

Revision ID: f7c2a4b91e0d
Revises: e2f5a9c17d3b
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "f7c2a4b91e0d"
down_revision = "e2f5a9c17d3b"
branch_labels = None
depends_on = None

ticket_priority = pg.ENUM("low", "medium", "high", "urgent", name="ticket_priority")
ticket_status = pg.ENUM("open", "in_progress", "resolved", "reopened", "closed", name="ticket_status")


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_number", sa.String(20), nullable=False, unique=True),
        sa.Column("raised_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("raised_by_role", sa.String(20), nullable=False),
        sa.Column("raised_by_org_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", ticket_priority, nullable=False, server_default="medium"),
        sa.Column("status", ticket_status, nullable=False, server_default="open"),
        sa.Column("related_module_type", sa.String(50), nullable=True),
        sa.Column("related_module_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_to_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_tickets_ticket_number", "support_tickets", ["ticket_number"])
    op.create_index("ix_support_tickets_raised_by_user_id", "support_tickets", ["raised_by_user_id"])
    op.create_index("ix_support_tickets_raised_by_role", "support_tickets", ["raised_by_role"])
    op.create_index("ix_support_tickets_raised_by_org_id", "support_tickets", ["raised_by_org_id"])
    op.create_index("ix_support_tickets_category", "support_tickets", ["category"])
    op.create_index("ix_support_tickets_priority", "support_tickets", ["priority"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])
    op.create_index("ix_support_tickets_assigned_to_user_id", "support_tickets", ["assigned_to_user_id"])
    op.create_index("ix_support_tickets_sla_due_at", "support_tickets", ["sla_due_at"])
    op.create_index("ix_support_tickets_created_at", "support_tickets", ["created_at"])

    op.create_table(
        "support_ticket_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", pg.UUID(as_uuid=True), sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sender_role", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_internal_note", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_ticket_messages_ticket_id", "support_ticket_messages", ["ticket_id"])
    op.create_index("ix_support_ticket_messages_created_at", "support_ticket_messages", ["created_at"])

    op.create_table(
        "support_ticket_attachments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", pg.UUID(as_uuid=True), sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", pg.UUID(as_uuid=True), sa.ForeignKey("support_ticket_messages.id", ondelete="CASCADE"), nullable=True),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_ticket_attachments_ticket_id", "support_ticket_attachments", ["ticket_id"])

    op.create_table(
        "support_routing_rules",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(100), nullable=False, unique=True),
        sa.Column("default_assignee_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("default_team", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_routing_rules_category", "support_routing_rules", ["category"])


def downgrade() -> None:
    op.drop_table("support_routing_rules")
    op.drop_table("support_ticket_attachments")
    op.drop_table("support_ticket_messages")
    op.drop_table("support_tickets")
    ticket_status.drop(op.get_bind(), checkfirst=True)
    ticket_priority.drop(op.get_bind(), checkfirst=True)

