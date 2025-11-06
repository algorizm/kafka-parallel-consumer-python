"""
Product Consumer Example
Portfolio version: Example consumer implementation for product data processing.

This consumer demonstrates:
- Multi-process consumer pattern
- Signal handling for graceful shutdown
- Concurrent request processing
- Offset management
"""
import logging
import multiprocessing
import os
import signal
import traceback

from dotenv import find_dotenv, load_dotenv

from src.base.base_process_consumer import ConsumerMain
from src.base.concurrent_logger import BatchQueueLog
from src.configs.constants import base_consumer_config

# Configuration
LOG_DIR = "logs"
LOG_NAME = "product_consumer"
NUMBER_OF_WORKERS = 10
CONCURRENT_REQUEST_THREAD_NUM = 15
QUEUE_MAX_SIZE = 200000


def task(_event: multiprocessing.Event):
    """
    Worker process task function.
    Each process runs this function to consume messages from Kafka.
    """
    # QueueLog 객체 프로세스 내에서 생성
    logger_cls = BatchQueueLog(log_dir=LOG_DIR, log_name=LOG_NAME)
    filename = base_consumer_config(file_name="product_consumer")
    path = find_dotenv(filename=filename)
    load_dotenv(path)

    prop_names = [
        "bootstrap.servers",
        "auto.offset.reset",
        "enable.auto.commit",
        "group.id",
        "fetch.min.bytes",
        "fetch.wait.max.ms",
        "max.poll.interval.ms",
    ]

    config = {}
    for p in prop_names:
        config.update({p: os.environ.get(p)})

    topic_name = os.environ.get("topic.name")
    work = ConsumerMain(
        config=config,
        topic_name=topic_name,
        logger_cls=logger_cls,
        event=_event,
        queue_max_size=QUEUE_MAX_SIZE,
    )

    try:
        work.start_concurrent_request(number=CONCURRENT_REQUEST_THREAD_NUM)
        work.consume()
    except Exception as e:
        logger_cls.log(logging.ERROR, f"Exception during consumer execution: {e}")


def main():
    """
    Main function to start multiple consumer processes.
    Handles graceful shutdown via signal handlers.
    """
    logger = BatchQueueLog(log_dir=LOG_DIR, log_name=LOG_NAME)
    process_event = multiprocessing.Event()
    process_list = []

    def signal_handler(signum, _):
        """Handle termination signals (SIGTERM, SIGINT)."""
        try:
            logger.log(
                logging.INFO,
                f"[{os.getpid()}]Received termination signal ({signum}) in main process.",
            )
            process_event.set()
        except Exception as e:
            logger.log(logging.ERROR, f"Exception in signal handler: {e}")

    # 메인 프로세스 SIGTERM, SIGINT (키보드 인터럽트 포함) 핸들러 설정
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    for i in range(NUMBER_OF_WORKERS):
        p = multiprocessing.Process(target=task, args=(process_event,), daemon=False)
        process_list.append(p)
        p.start()

    logger.log(
        logging.INFO,
        f"[{os.getpid()}]Started the {os.path.basename(__file__)} "
        f"process multi-process ({len(process_list)}) mode.",
    )

    try:
        for p in process_list:
            p.join()
    except KeyboardInterrupt:
        logger.log(logging.INFO, "KeyboardInterrupt received. Exiting...")
        process_event.set()
    except Exception as e1:
        logger.log(logging.ERROR, f"Exception:{e1}, traceback:{traceback.format_exc()}")
    finally:
        logger.log(logging.INFO, f"[{os.getpid()}]Main process terminated gracefully.")
        process_event.set()
        logger.wait_done()

        # 자식 프로세스 비 정상 종료인 경우 kill 처리
        for p in process_list:
            if p.is_alive():
                p.terminate()
                p.join()


if __name__ == "__main__":
    main()

