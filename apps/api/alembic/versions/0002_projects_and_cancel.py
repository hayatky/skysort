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
    job_foreign_keys = inspector.get_foreign_keys("jobs")
    has_project_fk = any(
        foreign_key.get("constrained_columns") == ["project_id"]
        and foreign_key.get("referred_table") == "projects"
        and foreign_key.get("referred_columns") == ["id"]
        for foreign_key in job_foreign_keys
    )
    required_job_columns = {
        "project_id",
        "cancel_requested",
        "canceled_at",
        "updated_at",
    }
    missing_job_columns = required_job_columns - job_columns
    if missing_job_columns or not has_project_fk:
        with op.batch_alter_table("jobs", recreate="always") as batch_op:
            if "project_id" in missing_job_columns:
                batch_op.add_column(sa.Column("project_id", sa.String(), nullable=True))
            if "cancel_requested" in missing_job_columns:
                batch_op.add_column(
                    sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())
                )
            if "canceled_at" in missing_job_columns:
                batch_op.add_column(sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))
            if "updated_at" in missing_job_columns:
                batch_op.add_column(
                    sa.Column(
                        "updated_at",
                        sa.DateTime(timezone=True),
                        nullable=False,
                        server_default=sa.text("CURRENT_TIMESTAMP"),
                    )
                )
            if not has_project_fk:
                batch_op.create_foreign_key("fk_jobs_project_id_projects", "projects", ["project_id"], ["id"])

    indexes = {index["name"] for index in inspector.get_indexes("jobs")}
    if ("project_id" in job_columns or "project_id" in missing_job_columns) and "ix_jobs_project_id" not in indexes:
        op.create_index("ix_jobs_project_id", "jobs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_project_id", table_name="jobs")
    with op.batch_alter_table("jobs", recreate="always") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("canceled_at")
        batch_op.drop_column("cancel_requested")
        batch_op.drop_column("project_id")
    op.drop_index("ix_projects_root_path", table_name="projects")
    op.drop_table("projects")
