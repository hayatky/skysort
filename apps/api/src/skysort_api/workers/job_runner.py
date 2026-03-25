from __future__ import annotations

import threading

from skysort_api.infra.database import session_scope
from skysort_api.services.analysis_service import reanalyze_photos, run_analysis


class JobRunner:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}

    def start(self, job_id: str) -> None:
        if job_id in self._threads and self._threads[job_id].is_alive():
            return
        thread = threading.Thread(target=self._run, args=(job_id,), daemon=True)
        self._threads[job_id] = thread
        thread.start()

    def start_photo_reanalysis(self, job_id: str, photo_ids: list[str], scope: str) -> None:
        key = f"{job_id}:photo:{','.join(sorted(photo_ids))}:{scope}"
        thread = threading.Thread(target=self._run_photo_reanalysis, args=(key, job_id, photo_ids, scope), daemon=True)
        self._threads[key] = thread
        thread.start()

    def _run(self, job_id: str) -> None:
        with session_scope() as session:
            run_analysis(session, job_id)

    def _run_photo_reanalysis(self, _key: str, job_id: str, photo_ids: list[str], scope: str) -> None:
        with session_scope() as session:
            reanalyze_photos(session, job_id, photo_ids, scope)


job_runner = JobRunner()
