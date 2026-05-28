"""technical relative scores"""

from alembic import op
import sqlalchemy as sa

revision = "0005_technical_relative_scores"
down_revision = "0004_visual_grouping_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "technical_scores" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("technical_scores")}
    with op.batch_alter_table("technical_scores") as batch_op:
        if "sharpness_rank" not in columns:
            batch_op.add_column(sa.Column("sharpness_rank", sa.Float(), nullable=True))
        if "exposure_rank" not in columns:
            batch_op.add_column(sa.Column("exposure_rank", sa.Float(), nullable=True))
        if "candidate_quality_score" not in columns:
            batch_op.add_column(sa.Column("candidate_quality_score", sa.Float(), nullable=True))
        if "reject_risk_score" not in columns:
            batch_op.add_column(sa.Column("reject_risk_score", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("technical_scores") as batch_op:
        batch_op.drop_column("reject_risk_score")
        batch_op.drop_column("candidate_quality_score")
        batch_op.drop_column("exposure_rank")
        batch_op.drop_column("sharpness_rank")
