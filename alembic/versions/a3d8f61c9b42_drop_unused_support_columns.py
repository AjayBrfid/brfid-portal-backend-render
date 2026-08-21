"""drop unused support ticket columns

Revision ID: a3d8f61c9b42
Revises: f7c2a4b91e0d
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "a3d8f61c9b42"
down_revision = "f7c2a4b91e0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("support_tickets", "related_module_type")
    op.drop_column("support_tickets", "related_module_id")
    op.drop_column("support_routing_rules", "default_team")


def downgrade() -> None:
    op.add_column("support_tickets", sa.Column("related_module_type", sa.String(50), nullable=True))
    op.add_column("support_tickets", sa.Column("related_module_id", pg.UUID(as_uuid=True), nullable=True))
    op.add_column("support_routing_rules", sa.Column("default_team", sa.String(100), nullable=True))
