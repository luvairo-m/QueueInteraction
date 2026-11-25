import asyncio
import json
import logging
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

import pika
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pika.adapters.blocking_connection import BlockingChannel
from pydantic import ValidationError
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from .broker import RESULTS, TASKS, consume, publish_confirmed
from .contracts import CsvCheckRequested, JobAccepted, JobCompleted, JobDone, JobInput
from .job_store import JobStore

log = logging.getLogger("uvicorn.error").getChild("queue")
project_dir = Path(__file__).resolve().parent.parent


def receive_result(
    channel: BlockingChannel,
    delivery: pika.spec.Basic.Deliver,
    _properties: pika.BasicProperties,
    body: bytes,
    *,
    jobs: JobStore,
) -> None:
    try:
        completed = JobCompleted.model_validate_json(body)
    except ValidationError:
        log.warning("Discarding invalid JobCompleted message")
        channel.basic_reject(delivery.delivery_tag, requeue=False)
        return

    jobs.complete(completed)
    channel.basic_ack(delivery.delivery_tag)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop, ready = Event(), Event()
    jobs = JobStore()
    app.state.jobs = jobs
    app.state.results_ready = ready
    receive = partial(receive_result, jobs=jobs)
    consumer = Thread(target=consume, args=(RESULTS, receive, stop, ready), daemon=True)
    consumer.start()
    try:
        yield
    finally:
        stop.set()
        await asyncio.to_thread(consumer.join, 6)


app = FastAPI(title="CSV Check Queue", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=project_dir / "web" / "assets"), name="assets")


@app.get("/", response_class=FileResponse, include_in_schema=False)
def demo() -> FileResponse:
    return FileResponse(project_dir / "web" / "index.html", media_type="text/html")


@app.get("/demo/example.json", response_class=FileResponse, include_in_schema=False)
def demo_example() -> FileResponse:
    return FileResponse(project_dir / "examples" / "job.json", media_type="application/json")


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, error: RequestValidationError) -> Response:
    details = [
        {"loc": issue["loc"], "msg": issue["msg"], "type": issue["type"]}
        for issue in error.errors()
    ]
    return Response(
        content=json.dumps({"detail": details}, ensure_ascii=True),
        media_type="application/json",
        status_code=422,
    )


@app.get("/health")
def health(request: Request) -> dict[str, str]:
    if not request.app.state.results_ready.is_set():
        raise HTTPException(status_code=503, detail="Results consumer is not ready")
    return {"status": "ok"}


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
def create_job(payload: JobInput, request: Request, response: Response) -> JobAccepted:
    if not request.app.state.results_ready.is_set():
        raise HTTPException(status_code=503, detail="RabbitMQ is not ready")

    jobs: JobStore = request.app.state.jobs
    task = CsvCheckRequested(id=uuid4(), csv=payload.csv)
    accepted = JobAccepted(id=task.id)
    jobs.register(accepted)

    try:
        publish_confirmed(TASKS, task.model_dump_json(), task.id, "CsvCheckRequested")
    except (pika.exceptions.AMQPError, OSError) as error:
        jobs.remove(task.id)
        log.warning("Could not confirm publication of %s: %s", task.id, error)
        raise HTTPException(status_code=503, detail="RabbitMQ publication could not be confirmed") from error

    response.headers["Location"] = f"/jobs/{task.id}"
    return accepted


@app.get("/jobs/{job_id}", response_model=JobDone | JobAccepted)
def get_job(job_id: UUID, request: Request) -> JobDone | JobAccepted:
    jobs: JobStore = request.app.state.jobs
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
