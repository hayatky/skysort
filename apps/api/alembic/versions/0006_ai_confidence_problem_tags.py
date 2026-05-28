"""ai confidence and problem tags"""

from alembic import op
import sqlalchemy as sa

revision = "0006_ai_confidence_problem_tags"
down_revision = "0005_technical_relative_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "photo_evaluations" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("photo_evaluations")}
    with op.batch_alter_table("photo_evaluations") as batch_op:
        if "ai_confidence_score" not in columns:
            batch_op.add_column(sa.Column("ai_confidence_score", sa.Float(), nullable=True))
        if "problem_tags_json" not in columns:
            batch_op.add_column(sa.Column("problem_tags_json", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("photo_evaluations") as batch_op:
        batch_op.drop_column("problem_tags_json")
        batch_op.drop_column("ai_confidence_score")
