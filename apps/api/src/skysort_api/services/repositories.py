from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from skysort_api.infra.models import AIResponse, Group, GroupMember, Job, JobFailure, Photo, PhotoEvaluation, RatingHistory, TechnicalScore


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, job: Job) -> None:
        self.session.add(job)

    def get(self, job_id: str) -> Job | None:
        return self.session.get(Job, job_id)

    def latest_for_root_path(self, root_path: str) -> Job | None:
        stmt = select(Job).where(Job.root_path == root_path).order_by(Job.started_at.desc().nullslast(), Job.id.desc())
        return self.session.scalars(stmt).first()

    def list_groups(self, job_id: str) -> list[Group]:
        return list(self.session.scalars(select(Group).where(Group.job_id == job_id).order_by(Group.created_at)))


class PhotoRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_many(self, photos: Iterable[Photo]) -> None:
        self.session.add_all(list(photos))

    def list_by_job(self, job_id: str, *, include_missing: bool = False) -> list[Photo]:
        stmt = select(Photo).where(Photo.job_id == job_id)
        if not include_missing:
            stmt = stmt.where(Photo.is_missing.is_(False))
        stmt = stmt.order_by(Photo.capture_order_index)
        return list(self.session.scalars(stmt))

    def get(self, photo_id: str) -> Photo | None:
        return self.session.get(Photo, photo_id)

    def list_for_paths(self, job_id: str) -> list[Photo]:
        return list(self.session.scalars(select(Photo).where(Photo.job_id == job_id)))


class GroupRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_job(self, job_id: str, groups: list[Group], members: list[GroupMember]) -> None:
        self.session.query(GroupMember).filter(GroupMember.group_id.in_(select(Group.id).where(Group.job_id == job_id))).delete(synchronize_session=False)
        self.session.query(Group).filter(Group.job_id == job_id).delete(synchronize_session=False)
        self.session.add_all(groups)
        self.session.add_all(members)

    def get(self, group_id: str) -> Group | None:
        return self.session.get(Group, group_id)

    def list_members(self, group_id: str) -> list[GroupMember]:
        return list(self.session.scalars(select(GroupMember).where(GroupMember.group_id == group_id).order_by(GroupMember.sort_order)))


class EvaluationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_technical(self, score: TechnicalScore) -> None:
        self.session.add(score)

    def add_ai_response(self, response: AIResponse) -> None:
        self.session.add(response)

    def add_evaluation(self, evaluation: PhotoEvaluation) -> PhotoEvaluation:
        existing = self.current_for_photo(evaluation.photo_id, evaluation.job_id)
        if existing is not None:
            existing.is_current = False
            existing.updated_at = evaluation.updated_at
            evaluation.version = existing.version + 1
        else:
            evaluation.version = 1
        evaluation.is_current = True
        self.session.add(evaluation)
        return evaluation

    def current_for_photo(self, photo_id: str, job_id: str) -> PhotoEvaluation | None:
        stmt = (
            select(PhotoEvaluation)
            .where(PhotoEvaluation.photo_id == photo_id, PhotoEvaluation.job_id == job_id, PhotoEvaluation.is_current.is_(True))
            .order_by(PhotoEvaluation.version.desc(), PhotoEvaluation.updated_at.desc())
        )
        return self.session.scalars(stmt).first()

    def latest_for_photo(self, photo_id: str, job_id: str) -> PhotoEvaluation | None:
        stmt = (
            select(PhotoEvaluation)
            .where(PhotoEvaluation.photo_id == photo_id, PhotoEvaluation.job_id == job_id)
            .order_by(PhotoEvaluation.version.desc(), PhotoEvaluation.updated_at.desc())
        )
        return self.session.scalars(stmt).first()

    def current_for_group(self, group_id: str, job_id: str) -> list[PhotoEvaluation]:
        stmt = (
            select(PhotoEvaluation)
            .where(
                PhotoEvaluation.group_id == group_id,
                PhotoEvaluation.job_id == job_id,
                PhotoEvaluation.is_current.is_(True),
            )
            .order_by(PhotoEvaluation.updated_at.desc())
        )
        return list(self.session.scalars(stmt))

    def list_for_job(self, job_id: str) -> list[PhotoEvaluation]:
        return list(self.session.scalars(select(PhotoEvaluation).where(PhotoEvaluation.job_id == job_id)))

    def list_current_for_job(self, job_id: str) -> list[PhotoEvaluation]:
        stmt = select(PhotoEvaluation).where(PhotoEvaluation.job_id == job_id, PhotoEvaluation.is_current.is_(True))
        return list(self.session.scalars(stmt))

    def technical_for_photo(self, photo_id: str, job_id: str) -> TechnicalScore | None:
        stmt = (
            select(TechnicalScore)
            .where(TechnicalScore.photo_id == photo_id, TechnicalScore.job_id == job_id)
            .order_by(TechnicalScore.updated_at.desc())
        )
        return self.session.scalars(stmt).first()

    def record_history(self, history: RatingHistory) -> None:
        self.session.add(history)


class FailureRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, failure: JobFailure) -> None:
        self.session.add(failure)

    def list_for_job(self, job_id: str) -> list[JobFailure]:
        stmt = select(JobFailure).where(JobFailure.job_id == job_id).order_by(JobFailure.created_at.desc())
        return list(self.session.scalars(stmt))
