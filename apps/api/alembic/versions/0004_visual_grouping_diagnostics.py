"""visual grouping diagnostics"""

from alembic import op
import sqlalchemy as sa

revision = "0004_visual_grouping_diagnostics"
down_revision = "0003_repair_jobs_project_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "photos" in tables:
        photo_columns = {column["name"] for column in inspector.get_columns("photos")}
        if "visual_features_json" not in photo_columns:
            op.add_column("photos", sa.Column("visual_features_json", sa.Text(), nullable=False, server_default="{}"))

    if "groups" in tables:
        group_columns = {column["name"] for column in inspector.get_columns("groups")}
        with op.batch_alter_table("groups") as batch_op:
            if "boundary_reason" not in group_columns:
                batch_op.add_column(sa.Column("boundary_reason", sa.String(), nullable=True))
            if "merge_suggested" not in group_columns:
                batch_op.add_column(sa.Column("merge_suggested", sa.Boolean(), nullable=False, server_default=sa.false()))
            if "merge_suggestion_reason" not in group_columns:
                batch_op.add_column(sa.Column("merge_suggestion_reason", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_column("merge_suggestion_reason")
        batch_op.drop_column("merge_suggested")
        batch_op.drop_column("boundary_reason")
    op.drop_column("photos", "visual_features_json")
