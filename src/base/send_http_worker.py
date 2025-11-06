import asyncio
import threading
from multiprocessing import Lock
from queue import Empty, Queue
from threading import Thread
from time import sleep
from typing import List

from src.utils.request import async_task_request_uri_queue, request_uri_no_session_map
from src.utils.structs import RequestURIMap
from src.utils.type import RequestType


class SendHttpWorker(Thread):
    def __init__(
        self,
        name: str,
        message_queue: Queue,
        offset_space: dict,
        lock: Lock,
        is_async: bool,
        **kwargs
    ):
        Thread.__init__(self)
        self.name = name
        self.daemon = True
        self.queue: Queue = message_queue
        self.offset_space = offset_space
        self.lock = lock
        self.is_async = is_async
        self.event = threading.Event()
        self.idx = kwargs["idx"]
        self.thread_id = kwargs["main_thread_id"]
        self.de_queue_count: list[int] = kwargs["de_queue_count"]
        self.de_queue_count_by_secs: list[int] = kwargs["de_queue_count_by_secs"]
        self.de_queue_count_each_thread: list[int] = kwargs[
            "de_queue_count_each_thread"
        ]

        if self.is_async:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    def dispose(self):
        if self.is_async:
            self.loop.close()

    def run(self) -> None:
        request_items: List[RequestURIMap] = None
        while not self.event.is_set():
            try:
                record = self.queue.get()
                if record is None:
                    break
                self.queue.task_done()
            except Empty:
                sleep(0.1)
                continue

            if self.is_async:
                self.async_process_http_requests(record)
            else:
                self.process_http_requests(record)

        else:
            # fixme event 시점에 각 스레드 처리한 offset(max) 정보 처리
            if request_items is not None:
                try:
                    self.lock.acquire()
                    _max_item = max(request_items, key=lambda x: x.commit_offset)
                    if _max_item.commit_partition in self.offset_space:
                        if (
                            _max_item.commit_offset
                            > self.offset_space[_max_item.commit_partition]
                        ):
                            self.offset_space[
                                _max_item.commit_partition
                            ] = _max_item.commit_offset
                    else:
                        self.offset_space[
                            _max_item.commit_partition
                        ] = _max_item.commit_offset
                finally:
                    self.lock.release()

    def process_http_requests(self, request_items: List[RequestURIMap]):
        try:
            for item in request_items:
                if item.request_type is not RequestType.NO_BEHAVIOR:
                    request_uri_no_session_map(worker_name=self.name, req_map=item)
        finally:
            try:
                self.lock.acquire()
                if request_items[0].commit_partition in self.offset_space:
                    # fixme dict key(partition) 해당 하는 offset 값이 더 큰 경우 대체
                    if (
                        request_items[0].commit_offset
                        > self.offset_space[request_items[0].commit_partition]
                    ):
                        self.offset_space[
                            request_items[0].commit_partition
                        ] = request_items[0].commit_offset
                else:
                    self.offset_space[
                        request_items[0].commit_partition
                    ] = request_items[0].commit_offset
                # fixme 1 건당 디큐 수행
                self.de_queue_count_by_secs[0] += 1
                self.de_queue_count_each_thread[self.idx] += 1
                if len(self.de_queue_count) >= 1:
                    self.de_queue_count[0] += 1
            finally:
                self.lock.release()

    def async_process_http_requests(self, request_items: List[RequestURIMap]):
        try:
            task = self.loop.create_task(async_task_request_uri_queue(request_items))
            self.loop.run_until_complete(task)
        finally:
            try:
                self.lock.acquire()
                _max_item = max(request_items, key=lambda x: x.commit_offset)
                if _max_item.commit_partition in self.offset_space:
                    if (
                        _max_item.commit_offset
                        > self.offset_space[_max_item.commit_partition]
                    ):
                        self.offset_space[
                            _max_item.commit_partition
                        ] = _max_item.commit_offset
                else:
                    self.offset_space[
                        _max_item.commit_partition
                    ] = _max_item.commit_offset
                # fixme 1 건당 디큐 수행
                self.de_queue_count_by_secs[0] += 1
                self.de_queue_count_each_thread[self.idx] += 1
                if len(self.de_queue_count) >= 1:
                    self.de_queue_count[0] += 1
            finally:
                self.lock.release()

