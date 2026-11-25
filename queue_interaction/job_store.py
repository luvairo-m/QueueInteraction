import logging
from threading import Lock
from uuid import UUID

from .contracts import JobAccepted, JobCompleted, JobDone

log = logging.getLogger("uvicorn.error").getChild("queue")


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[UUID, JobAccepted | JobDone] = {}
        self._lock = Lock()

    def register(self, job: JobAccepted) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: UUID) -> JobAccepted | JobDone | None:
        with self._lock:
            return self._jobs.get(job_id)

    def remove(self, job_id: UUID) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def complete(self, event: JobCompleted) -> None:
        with self._lock:
            current = self._jobs.get(event.id)
            if isinstance(current, JobAccepted):
                self._jobs[event.id] = JobDone(id=event.id, result=event.result, completed_at=event.completed_at)
                log.info("Saved result for %s", event.id)
            elif isinstance(current, JobDone):
                log.info("Ignored duplicate result for %s", event.id)
            else:
                log.warning("Result for unknown job %s", event.id)
