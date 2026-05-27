"""projects and cancellable jobs"""

from alembic import op
import sqlalchemy as sa

revision = "0002_projects_and_cancel"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "projects" not in tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("root_path", sa.String(), nullable=False),
            sa.Column("recursive", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("file_types_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("last_job_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_projects_root_path", "projects", ["root_path"], unique=True)

    job_columns = {column["name"] for column in inspector.get_columns("jobs")}
    if "project_id" not in job_columns:
        op.add_column("jobs", sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=True))
        op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
    if "cancel_requested" not in job_columns:
        op.add_column("jobs", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "canceled_at" not in job_columns:
        op.add_column("jobs", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))
    if "updated_at" not in job_columns:
        op.add_column("jobs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))


def downgrade() -> None:
    op.drop_column("jobs", "updated_at")
    op.drop_column("jobs", "canceled_at")
    op.drop_column("jobs", "cancel_requested")
    op.drop_index("ix_jobs_project_id", table_name="jobs")
    op.drop_column("jobs", "project_id")
    op.drop_index("ix_projects_root_path", table_name="projects")
    op.drop_table("projects")
