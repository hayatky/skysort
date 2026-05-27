"""repair jobs project foreign key"""

from alembic import op
import sqlalchemy as sa

revision = "0003_repair_jobs_project_fk"
down_revision = "0002_projects_and_cancel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "jobs" not in tables or "projects" not in tables:
        return

    job_columns = {column["name"] for column in inspector.get_columns("jobs")}
    if "project_id" not in job_columns:
        return

    has_project_fk = any(
        foreign_key.get("constrained_columns") == ["project_id"]
        and foreign_key.get("referred_table") == "projects"
        and foreign_key.get("referred_columns") == ["id"]
        for foreign_key in inspector.get_foreign_keys("jobs")
    )
    if has_project_fk:
        return

    with op.batch_alter_table("jobs", recreate="always") as batch_op:
        batch_op.create_foreign_key("fk_jobs_project_id_projects", "projects", ["project_id"], ["id"])


def downgrade() -> None:
    pass
