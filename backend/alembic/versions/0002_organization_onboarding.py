"""Organization profile and administrator onboarding."""
from alembic import op
import sqlalchemy as sa

revision = "0002_organization_onboarding"
down_revision = "ed7250265465"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("industry", sa.String(100)))
    op.add_column("organizations", sa.Column("size", sa.String(20)))
    op.add_column("organizations", sa.Column("logo_data", sa.Text()))
    op.add_column("invitations", sa.Column("temporary_password_hash", sa.String(100)))
    op.add_column("invitations", sa.Column("delivery_id", sa.String(36)))
    op.create_foreign_key("fk_invitations_delivery_id", "invitations", "email_outbox", ["delivery_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_invitations_delivery_id", "invitations", type_="foreignkey")
    op.drop_column("invitations", "delivery_id")
    op.drop_column("invitations", "temporary_password_hash")
    op.drop_column("organizations", "logo_data")
    op.drop_column("organizations", "size")
    op.drop_column("organizations", "industry")
