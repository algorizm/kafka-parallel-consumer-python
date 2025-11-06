import logging
import logging.config
import logging.handlers
import queue
from multiprocessing import JoinableQueue
from threading import Thread
from time import sleep

from src.configs.constants import (
    COMMIT_OFFSET_LOG_LEVEL,
    EACH_REQUEST_THREAD_LOG_LEVEL,
    MESSAGE_COUNT_LOG_LEVEL,
    REQUEST_TIME_LOG_LEVEL,
    RETRY_REQUEST_LOG_LEVEL,
)


class BatchQueueLog:
    def __init__(self, log_dir: str, log_name: str):
        self._shutdown = False
        self._queue = JoinableQueue()
        self._log_batch_size = 50
        self._logger_thread = Thread(target=self.logger_thread_func, daemon=True)
        self._logger_thread.start()
        self._size = 0

        # fixme https://pypi.org/project/concurrent-log-handler/
        # fixme https://github.com/Preston-Landers/concurrent-log-handler

        ld = {
            "version": 1,
            "formatters": {
                "detailed": {
                    "class": "logging.Formatter",
                    "format": "%(asctime)s %(name)-8s %(levelname)-8s %(processName)-1s %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": "INFO",
                },
                "rotating_info": {
                    "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                    "filename": f"{log_dir}/{log_name}.log",
                    "mode": "a",
                    "maxBytes": 1024 * 1024 * 10,  # 10MB 단위
                    "backupCount": 10,
                    "encoding": "utf-8",
                    "delay": False,
                    "formatter": "detailed",
                    "level": "INFO",
                },
                "rotating_errors": {
                    "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                    "filename": f"{log_dir}/{log_name}-errors.log",
                    "mode": "a",
                    "maxBytes": 1024 * 1024 * 10,  # 10MB 단위
                    "backupCount": 20,
                    "encoding": "utf-8",
                    "delay": False,
                    "formatter": "detailed",
                    "level": "ERROR",
                },
                "rotating_offset": {
                    "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                    "filename": f"{log_dir}/{log_name}-offset.log",
                    "mode": "a",
                    "maxBytes": 1024 * 1024 * 10,  # 10MB 단위
                    "backupCount": 5,
                    "encoding": "utf-8",
                    "delay": False,
                    "formatter": "detailed",
                    "level": "DEBUG",
                },
                "rotating_count": {
                    "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                    "filename": f"{log_dir}/{log_name}-count.log",
                    "mode": "a",
                    "maxBytes": 1024 * 1024 * 10,  # 10MB 단위
                    "backupCount": 5,
                    "encoding": "utf-8",
                    "delay": False,
                    "formatter": "detailed",
                    "level": "DEBUG",
                },
                "rotating_request": {
                    "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                    "filename": f"{log_dir}/{log_name}-request.log",
                    "mode": "a",
                    "maxBytes": 1024 * 1024 * 10,  # 10MB 단위
                    "backupCount": 5,
                    "encoding": "utf-8",
                    "delay": False,
                    "formatter": "detailed",
                    "level": "DEBUG",
                },
                "rotating_thread": {
                    "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                    "filename": f"{log_dir}/{log_name}-thread.log",
                    "mode": "a",
                    "maxBytes": 1024 * 1024 * 10,  # 10MB 단위
                    "backupCount": 5,
                    "encoding": "utf-8",
                    "delay": False,
                    "formatter": "detailed",
                    "level": "DEBUG",
                },
                "rotating_retry": {
                    "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                    "filename": f"{log_dir}/{log_name}-retry.log",
                    "mode": "a",
                    "maxBytes": 1024 * 1024 * 10,  # 10MB 단위
                    "backupCount": 5,
                    "encoding": "utf-8",
                    "delay": False,
                    "formatter": "detailed",
                    "level": "DEBUG",
                },
            },
            "loggers": {
                "info": {"handlers": ["rotating_info"]},
                "error": {"handlers": ["rotating_errors"]},
                "offset": {"handlers": ["rotating_offset"]},
                "count": {"handlers": ["rotating_count"], "propagate": False},
                "request": {"handlers": ["rotating_request"], "propagate": False},
                "thread": {"handlers": ["rotating_thread"], "propagate": False},
                "retry": {"handlers": ["rotating_retry"], "propagate": False},
            },
            "root": {"level": "DEBUG", "handlers": ["console"]},
        }
        logging.addLevelName(MESSAGE_COUNT_LOG_LEVEL, "count")
        logging.addLevelName(COMMIT_OFFSET_LOG_LEVEL, "offset")
        logging.addLevelName(REQUEST_TIME_LOG_LEVEL, "request")
        logging.addLevelName(EACH_REQUEST_THREAD_LOG_LEVEL, "thread")
        logging.addLevelName(RETRY_REQUEST_LOG_LEVEL, "retry")
        logging.config.dictConfig(ld)

    @property
    def queue(self):
        return self._queue

    @property
    def logger_thread(self):
        return self._logger_thread

    def wait_done(self):
        self._shutdown = True
        self.queue.put(None)
        self.queue.join()

        self.queue.close()
        self.queue.join_thread()

        if self._logger_thread.is_alive():
            self._logger_thread.join(timeout=5)

    def get_qsize(self):
        try:
            # macOS 에서 qsize() 예외 발생 시 except 블록 실행
            return self._queue.qsize()
        except (NotImplementedError, OSError):
            # Mac 에서 발생 하는 예외 처리
            return self._size

    def put_queue(self, item):
        self.queue.put(item)
        self._size += 1

    def get_queue(self):
        item = self.queue.get()
        self._size -= 1
        return item

    def logger_thread_func(self):
        while True:
            try:
                # 배치 처리
                records = []
                for _ in range(self._log_batch_size):
                    if self.queue.empty():
                        break
                    record = self.get_queue()
                    if record is None:
                        self.queue.task_done()
                        break
                    records.append(record)

                # 로그 처리
                if records:
                    for record in records:
                        if record is not None:
                            logger = logging.getLogger(record.name)
                            logger.handle(record)
                            self._queue.task_done()
                else:
                    sleep(1)

            except queue.Empty:
                if self._shutdown:
                    break
                sleep(1)
                continue
            except Exception as e:
                self.log(logging.ERROR, str(e))
                if self._shutdown:
                    break

    def log(self, level: int, msg: str):
        if level == logging.INFO:
            logger = logging.getLogger("info")
        elif level == logging.ERROR:
            logger = logging.getLogger("error")
        elif level == COMMIT_OFFSET_LOG_LEVEL:
            logger = logging.getLogger("offset")
        elif level == MESSAGE_COUNT_LOG_LEVEL:
            logger = logging.getLogger("count")
        elif level == REQUEST_TIME_LOG_LEVEL:
            logger = logging.getLogger("request")
        elif level == EACH_REQUEST_THREAD_LOG_LEVEL:
            logger = logging.getLogger("thread")
        elif level == RETRY_REQUEST_LOG_LEVEL:
            logger = logging.getLogger("retry")
        else:
            logger = logging.getLogger("info")

        record = logging.LogRecord(
            name=logger.name,
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=None,
            exc_info=None,
        )
        # 로그 메시지 큐에 추가
        self.put_queue(record)
