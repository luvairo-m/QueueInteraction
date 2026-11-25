import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from threading import Event
from uuid import UUID

import pika
from pika.adapters.blocking_connection import BlockingChannel

TASKS = "tasks"
RESULTS = "results"
DeliveryHandler = Callable[[BlockingChannel, pika.spec.Basic.Deliver, pika.BasicProperties, bytes], None]
log = logging.getLogger(__name__)


@contextmanager
def connect() -> Iterator[pika.BlockingConnection]:
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=os.environ.get("RABBITMQ_HOST", "rabbitmq"),
            credentials=pika.PlainCredentials(
                os.environ.get("RABBITMQ_DEFAULT_USER", "queue_demo"),
                os.environ.get("RABBITMQ_DEFAULT_PASS", "queue_demo"),
            ),
            heartbeat=15,
            socket_timeout=2,
            stack_timeout=4,
            blocked_connection_timeout=4,
        )
    )
    try:
        yield connection
    finally:
        if connection.is_open:
            with suppress(pika.exceptions.AMQPError, OSError):
                connection.close()


def declare_queues(channel: BlockingChannel) -> None:
    for queue in (TASKS, RESULTS):
        channel.queue_declare(queue=queue, durable=True, arguments={"x-queue-type": "classic"})


def publish(channel: BlockingChannel, queue: str, body: str, job_id: UUID, kind: str) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=body.encode("utf-8"),
        mandatory=True,
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=str(job_id),
            type=kind,
        ),
    )


def publish_confirmed(queue: str, body: str, job_id: UUID, kind: str) -> None:
    with connect() as connection:
        channel = connection.channel()
        channel.confirm_delivery()
        publish(channel, queue, body, job_id, kind)


def consume(
    queue: str,
    handler: DeliveryHandler,
    stop: Event,
    ready: Event,
    *,
    confirms: bool = False,
) -> None:
    def on_cancel(_frame) -> None:
        log.warning("Broker cancelled the consumer for %s", queue)
        ready.clear()

    while not stop.is_set():
        try:
            with connect() as connection:
                channel = connection.channel()
                declare_queues(channel)

                if confirms:
                    channel.confirm_delivery()

                channel.basic_qos(prefetch_count=1)
                channel.add_on_cancel_callback(on_cancel)
                channel.basic_consume(queue, handler, auto_ack=False)

                ready.set()
                log.info("Consuming %s", queue)

                while ready.is_set() and channel.is_open and not stop.is_set():
                    connection.process_data_events(time_limit=0.5)

        except (pika.exceptions.AMQPError, OSError) as error:
            log.warning("Consumer for %s disconnected: %s", queue, error)
        finally:
            ready.clear()

        stop.wait(1)
