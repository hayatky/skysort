"""initial schema"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "jobs" not in tables:
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("root_path", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("imported_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("grouped_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("technically_scored_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("semantically_scored_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("provisional_rated_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("final_rated_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_stage", sa.String(), nullable=False, server_default="queued"),
            sa.Column("error_messages_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("settings_snapshot_json", sa.Text(), nullable=False),
            sa.Column("app_version", sa.String(), nullable=False),
            sa.Column("model_name", sa.String(), nullable=False),
            sa.Column("prompt_template_hash", sa.String(), nullable=False),
            sa.Column("response_schema_version", sa.String(), nullable=False),
        )
    if "photos" not in tables:
        op.create_table(
            "photos",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False, index=True),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_hash", sa.String(), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("file_mtime", sa.Float(), nullable=False),
            sa.Column("capture_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("capture_timestamp_ms", sa.BigInteger(), nullable=True),
            sa.Column("capture_order_index", sa.Integer(), nullable=False),
            sa.Column("camera_model", sa.String(), nullable=True),
            sa.Column("lens_model", sa.String(), nullable=True),
            sa.Column("focal_length", sa.Float(), nullable=True),
            sa.Column("shutter_speed", sa.String(), nullable=True),
            sa.Column("aperture", sa.Float(), nullable=True),
            sa.Column("iso", sa.Integer(), nullable=True),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("orientation", sa.Integer(), nullable=True),
            sa.Column("preview_path", sa.String(), nullable=True),
            sa.Column("thumb_path", sa.String(), nullable=True),
            sa.Column("is_missing", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "groups" not in tables:
        op.create_table(
            "groups",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False, index=True),
            sa.Column("representative_photo_id", sa.String(), nullable=True),
            sa.Column("best_photo_id", sa.String(), nullable=True),
            sa.Column("group_size", sa.Integer(), nullable=False),
            sa.Column("group_start_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("group_end_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("diversity_score", sa.Float(), nullable=True),
            sa.Column("stale_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("stale_reason", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "group_members" not in tables:
        op.create_table(
            "group_members",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("group_id", sa.String(), sa.ForeignKey("groups.id"), nullable=False, index=True),
            sa.Column("photo_id", sa.String(), sa.ForeignKey("photos.id"), nullable=False, index=True),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("similarity_score", sa.Float(), nullable=True),
            sa.Column("manually_assigned_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "technical_scores" not in tables:
        op.create_table(
            "technical_scores",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("photo_id", sa.String(), sa.ForeignKey("photos.id"), nullable=False, index=True),
            sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False, index=True),
            sa.Column("sharpness_score", sa.Float(), nullable=False),
            sa.Column("motion_blur_score", sa.Float(), nullable=False),
            sa.Column("highlight_clip_ratio", sa.Float(), nullable=False),
            sa.Column("shadow_clip_ratio", sa.Float(), nullable=False),
            sa.Column("technical_score_total", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ai_responses" not in tables:
        op.create_table(
            "ai_responses",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False, index=True),
            sa.Column("photo_id", sa.String(), sa.ForeignKey("photos.id"), nullable=True, index=True),
            sa.Column("group_id", sa.String(), sa.ForeignKey("groups.id"), nullable=True, index=True),
            sa.Column("phase", sa.String(), nullable=False),
            sa.Column("model_name", sa.String(), nullable=False),
            sa.Column("prompt_template_name", sa.String(), nullable=False),
            sa.Column("prompt_template_hash", sa.String(), nullable=False),
            sa.Column("response_schema_version", sa.String(), nullable=False),
            sa.Column("request_payload", sa.Text(), nullable=False),
            sa.Column("response_json", sa.Text(), nullable=True),
            sa.Column("raw_response_text", sa.Text(), nullable=True),
            sa.Column("raw_response_path", sa.String(), nullable=True),
            sa.Column("target_photo_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("response_status", sa.String(), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "photo_evaluations" not in tables:
        op.create_table(
            "photo_evaluations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("photo_id", sa.String(), sa.ForeignKey("photos.id"), nullable=False, index=True),
            sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False, index=True),
            sa.Column("group_id", sa.String(), sa.ForeignKey("groups.id"), nullable=True, index=True),
            sa.Column("semantic_score", sa.Float(), nullable=True),
            sa.Column("composition_score", sa.Float(), nullable=True),
            sa.Column("subject_state_score", sa.Float(), nullable=True),
            sa.Column("rarity_score", sa.Float(), nullable=True),
            sa.Column("provisional_rating", sa.Integer(), nullable=True),
            sa.Column("provisional_selection_status", sa.String(), nullable=False, server_default="normal"),
            sa.Column("rating", sa.Integer(), nullable=True),
            sa.Column("selection_status", sa.String(), nullable=False, server_default="normal"),
            sa.Column("evaluation_status", sa.String(), nullable=False),
            sa.Column("pick_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("best_cut_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("reviewed_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("ai_reason", sa.Text(), nullable=True),
            sa.Column("user_override_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("stale_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("stale_reason", sa.String(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    else:
        columns = {column["name"] for column in inspector.get_columns("photo_evaluations")}
        if "version" not in columns:
            op.add_column("photo_evaluations", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        if "is_current" not in columns:
            op.add_column("photo_evaluations", sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "rating_history" not in tables:
        op.create_table(
            "rating_history",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("photo_id", sa.String(), sa.ForeignKey("photos.id"), nullable=False, index=True),
            sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False, index=True),
            sa.Column("old_rating", sa.Integer(), nullable=True),
            sa.Column("new_rating", sa.Integer(), nullable=True),
            sa.Column("old_selection_status", sa.String(), nullable=True),
            sa.Column("new_selection_status", sa.String(), nullable=True),
            sa.Column("changed_by_user", sa.Boolean(), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.String(), nullable=False),
        )
    if "job_failures" not in tables:
        op.create_table(
            "job_failures",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False, index=True),
            sa.Column("photo_id", sa.String(), sa.ForeignKey("photos.id"), nullable=True, index=True),
            sa.Column("group_id", sa.String(), sa.ForeignKey("groups.id"), nullable=True, index=True),
            sa.Column("stage", sa.String(), nullable=False),
            sa.Column("reason_code", sa.String(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("job_failures")
    op.drop_table("rating_history")
    op.drop_table("photo_evaluations")
    op.drop_table("ai_responses")
    op.drop_table("technical_scores")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("photos")
    op.drop_table("jobs")
