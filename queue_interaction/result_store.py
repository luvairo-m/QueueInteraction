import os
from pathlib import Path
from uuid import UUID


class ResultStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def load(self, job_id: UUID) -> str | None:
        try:
            return self._path(job_id).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def save(self, job_id: UUID, event_json: str) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._path(job_id)
        temporary = path.with_suffix(".tmp")

        with temporary.open("w", encoding="utf-8") as file:
            file.write(event_json)
            file.flush()
            os.fsync(file.fileno())

        temporary.replace(path)

    def _path(self, job_id: UUID) -> Path:
        return self._directory / f"{job_id}.json"
