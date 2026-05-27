from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    root_path: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    recursive: Mapped[bool] = mapped_column(Boolean, default=True)
    file_types_json: Mapped[str] = mapped_column(Text, default="[]")
    last_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="project")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    root_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    imported_files: Mapped[int] = mapped_column(Integer, default=0)
    grouped_files: Mapped[int] = mapped_column(Integer, default=0)
    technically_scored_files: Mapped[int] = mapped_column(Integer, default=0)
    semantically_scored_files: Mapped[int] = mapped_column(Integer, default=0)
    provisional_rated_files: Mapped[int] = mapped_column(Integer, default=0)
    final_rated_files: Mapped[int] = mapped_column(Integer, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str] = mapped_column(String, default="queued")
    error_messages_json: Mapped[str] = mapped_column(Text, default="[]")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settings_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_template_hash: Mapped[str] = mapped_column(String, nullable=False)
    response_schema_version: Mapped[str] = mapped_column(String, nullable=False)

    project: Mapped[Project | None] = relationship(back_populates="jobs")
    photos: Mapped[list["Photo"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_mtime: Mapped[float] = mapped_column(Float, nullable=False)
    capture_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capture_timestamp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capture_order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    camera_model: Mapped[str | None] = mapped_column(String, nullable=True)
    lens_model: Mapped[str | None] = mapped_column(String, nullable=True)
    focal_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    shutter_speed: Mapped[str | None] = mapped_column(String, nullable=True)
    aperture: Mapped[float | None] = mapped_column(Float, nullable=True)
    iso: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orientation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String, nullable=True)
    thumb_path: Mapped[str | None] = mapped_column(String, nullable=True)
    is_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[Job] = relationship(back_populates="photos")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    representative_photo_id: Mapped[str | None] = mapped_column(String, nullable=True)
    best_photo_id: Mapped[str | None] = mapped_column(String, nullable=True)
    group_size: Mapped[int] = mapped_column(Integer, nullable=False)
    group_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    group_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    diversity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    stale_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GroupMember(Base):
    __tablename__ = "group_members"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"), index=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    manually_assigned_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TechnicalScore(Base):
    __tablename__ = "technical_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    sharpness_score: Mapped[float] = mapped_column(Float, nullable=False)
    motion_blur_score: Mapped[float] = mapped_column(Float, nullable=False)
    highlight_clip_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    shadow_clip_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    technical_score_total: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIResponse(Base):
    __tablename__ = "ai_responses"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("photos.id"), nullable=True, index=True)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("groups.id"), nullable=True, index=True)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_template_name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_template_hash: Mapped[str] = mapped_column(String, nullable=False)
    response_schema_version: Mapped[str] = mapped_column(String, nullable=False)
    request_payload: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_path: Mapped[str | None] = mapped_column(String, nullable=True)
    target_photo_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    response_status: Mapped[str] = mapped_column(String, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PhotoEvaluation(Base):
    __tablename__ = "photo_evaluations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("groups.id"), nullable=True, index=True)
    semantic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    composition_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    subject_state_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    provisional_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provisional_selection_status: Mapped[str] = mapped_column(String, default="normal")
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_status: Mapped[str] = mapped_column(String, default="normal")
    evaluation_status: Mapped[str] = mapped_column(String, nullable=False)
    pick_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    best_cut_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_override_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RatingHistory(Base):
    __tablename__ = "rating_history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    old_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_selection_status: Mapped[str | None] = mapped_column(String, nullable=True)
    new_selection_status: Mapped[str | None] = mapped_column(String, nullable=True)
    changed_by_user: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reason: Mapped[str] = mapped_column(String, nullable=False)


class JobFailure(Base):
    __tablename__ = "job_failures"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("photos.id"), nullable=True, index=True)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("groups.id"), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
