import logging
import os
import signal
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from threading import Event

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pydantic import ValidationError

from .broker import RESULTS, TASKS, consume, publish
from .contracts import CsvCheckRequested, JobCompleted
from .csv_check import CsvFormatError, check_csv
from .result_store import ResultStore

log = logging.getLogger(__name__)


def process_task(task: CsvCheckRequested, connection: pika.BlockingConnection) -> JobCompleted:
    result = check_csv(task.csv)
    log.info("Processing %s", task.id)
    connection.sleep(2.5)

    return JobCompleted(id=task.id, result=result, completed_at=datetime.now(timezone.utc))


def complete_task(
    task: CsvCheckRequested,
    channel: BlockingChannel,
    delivery: pika.spec.Basic.Deliver,
    store: ResultStore,
    pause_before_ack: float,
) -> None:
    log.info("Received %s redelivered=%s", task.id, delivery.redelivered)
    event_json = store.load(task.id)
    computed = event_json is None

    if event_json is None:
        completed = process_task(task, channel.connection)
        event_json = completed.model_dump_json(by_alias=True)
        store.save(task.id, event_json)
    else:
        log.info("Reusing saved result for %s", task.id)

    publish(channel, RESULTS, event_json, task.id, "JobCompleted")

    if computed and pause_before_ack > 0:
        log.info("Result confirmed for %s, pausing %.0fs before ACK", task.id, pause_before_ack)
        channel.connection.sleep(pause_before_ack)

    channel.basic_ack(delivery.delivery_tag)
    log.info("ACK %s", task.id)


def handle_task(
    channel: BlockingChannel,
    delivery: pika.spec.Basic.Deliver,
    _properties: pika.BasicProperties,
    body: bytes,
    *,
    store: ResultStore,
    pause_before_ack: float,
) -> None:
    try:
        task = CsvCheckRequested.model_validate_json(body)
        complete_task(task, channel, delivery, store, pause_before_ack)
    except (ValidationError, CsvFormatError):
        log.warning("Discarding invalid CsvCheckRequested message")
        channel.basic_reject(delivery.delivery_tag, requeue=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("pika").setLevel(logging.WARNING)

    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    result_dir = Path(os.environ.get("WORKER_RESULT_DIR", "/var/lib/queue-interaction/results"))
    pause_before_ack = float(os.environ.get("DEMO_PAUSE_BEFORE_ACK", "0"))
    handle = partial(handle_task, store=ResultStore(result_dir), pause_before_ack=pause_before_ack)

    consume(TASKS, handle, stop, Event(), confirms=True)


if __name__ == "__main__":
    main()
