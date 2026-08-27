from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    attempts: int = 0
    error: str | None = None


class DurableJobRunner:
    """Local worker seam; production maps this queue to SQS and a DLQ."""

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()

    def submit(self, kind: str, work: Callable[[], None]) -> Job:
        job = Job(id=f"job-{uuid.uuid4().hex[:10]}", kind=kind)
        with self.lock:
            self.jobs[job.id] = job
        thread = threading.Thread(target=self._run, args=(job, work), daemon=True)
        thread.start()
        return job

    def _run(self, job: Job, work: Callable[[], None]) -> None:
        for attempt in range(1, 4):
            try:
                with self.lock:
                    job.status, job.attempts = "running", attempt
                work()
                with self.lock:
                    job.status = "completed"
                return
            except Exception as exc:  # noqa: BLE001 - the job must become observable
                with self.lock:
                    job.error = str(exc)
                time.sleep(0.05 * attempt)
        with self.lock:
            job.status = "dead_letter"

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)


runner = DurableJobRunner()
