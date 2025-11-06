import logging
import os
import queue
from datetime import datetime
from threading import Event, Thread
from time import sleep
from typing import List

import requests

from src.configs.constants import (
    HTTP_REQUEST_RETRY_LIMIT,
    HTTP_REQUEST_TIMEOUT,
    RETRY_REQUEST_LOG_LEVEL,
)
from src.configs.env import APP_ENVIRONMENT
from src.utils.slack import send_slack_notification, send_slack_alert
from src.utils.structs import RequestURIMap
from src.utils.type import RequestType


class SendHttpWorker(Thread):
    def __init__(
        self,
        name: str,
        event: Event,
        message_queue: queue.Queue,
        offset_queue: queue.SimpleQueue,
        idx: int,
        main_process_id: int,
        de_queue_count: List[int],
        de_queue_count_by_secs: List[int],
        de_queue_count_each_thread: List[int],
    ):
        Thread.__init__(self)
        self.name = name
        self.daemon = True
        self.queue = message_queue
        self.offset_queue = offset_queue

        self.event = event
        self.idx = idx
        self.process_id = main_process_id
        self.de_queue_count: List[int] = de_queue_count
        self.de_queue_count_by_secs: List[int] = de_queue_count_by_secs
        self.de_queue_count_each_thread: List[int] = de_queue_count_each_thread

    def dispose(self):
        pass

    def run(self) -> None:
        request_items: List[RequestURIMap] = list()
        while not self.event.is_set():
            try:
                record = self.queue.get(timeout=1)
                if record is None:
                    break
            except queue.Empty:
                sleep(0.5)
                continue

            self.process_http_requests(record)

        if request_items is not None:
            # fixme event 시점에 각 스레드 처리한 offset(max) 정보 처리
            self.update_offset_queue(request_items)

    def request_uri_no_session_map(self, worker_name: str, req_map: RequestURIMap):
        try:
            headers = {"Content-Type": "application/json", "charset": "utf-8"}

            with requests.session() as session:
                st = datetime.now()
                req_map.request_body.update(
                    {"request_timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")}
                )

                if not self.event.is_set():
                    if "__C" in str(req_map.request_type):
                        response = session.post(
                            req_map.request_uri,
                            headers=headers,
                            json=req_map.request_body,
                            timeout=HTTP_REQUEST_TIMEOUT,
                        )
                    elif "__U" in str(req_map.request_type):
                        response = session.put(
                            req_map.request_uri,
                            headers=headers,
                            json=req_map.request_body,
                            timeout=HTTP_REQUEST_TIMEOUT,
                        )
                    elif "__D" in str(req_map.request_type):
                        response = session.delete(
                            req_map.request_uri,
                            json=req_map.request_body,
                            timeout=HTTP_REQUEST_TIMEOUT,
                        )
                    et = datetime.now()

                    msg = (
                        f"[{os.uname().nodename}]{worker_name}req({st.strftime('%M:%S.%f')}), "
                        f"res({et.strftime('%M:%S.%f')}), "
                        f"elapsed({(et-st).total_seconds()}), type:{req_map.request_type}, uri:{req_map.request_uri}, "
                        f"status:{response.status_code}, response:{response.text}, body:{req_map.request_body}, "
                        f"partition:{req_map.commit_partition}, offset:{req_map.commit_offset}"
                    )

                    logger = logging.getLogger("request")
                    logger.log(logging.INFO, msg)
        except requests.exceptions.Timeout as t1:
            msg = (
                f"[{os.uname().nodename}]{worker_name}timeout request type:{req_map.request_type},"
                f"uri:{req_map.request_uri}, exception:{t1}, "
                f"request_body:{req_map.request_body}"
            )
            logger = logging.getLogger("error")
            logger.log(logging.ERROR, msg)

            # fixme 개발 서버 slack 알림 제외 (Portfolio: Slack channel link removed)
            if APP_ENVIRONMENT == "PROD":
                send_slack_alert(text=msg)
        except Exception as e1:
            self.retry_request_uri_no_session_map(
                worker_name=worker_name, req_map=req_map, retry_cnt=1, errmsg=e1
            )
        return NotImplemented

    def retry_request_uri_no_session_map(
        self, worker_name: str, req_map: RequestURIMap, retry_cnt: int, errmsg
    ):
        if retry_cnt <= HTTP_REQUEST_RETRY_LIMIT:
            headers = {"Content-Type": "application/json", "charset": "utf-8"}
            try:
                with requests.session() as session:
                    st = datetime.now()

                    if not self.event.is_set():
                        if "__C" in str(req_map.request_type):
                            response = session.post(
                                req_map.request_uri,
                                headers=headers,
                                json=req_map.request_body,
                                timeout=HTTP_REQUEST_TIMEOUT,
                            )
                        elif "__U" in str(req_map.request_type):
                            response = session.put(
                                req_map.request_uri,
                                headers=headers,
                                json=req_map.request_body,
                                timeout=HTTP_REQUEST_TIMEOUT,
                            )
                        elif "__D" in str(req_map.request_type):
                            response = session.delete(
                                req_map.request_uri,
                                json=req_map.request_body,
                                timeout=HTTP_REQUEST_TIMEOUT,
                            )
                        et = datetime.now()
                        msg = (
                            f"[{os.uname().nodename}]{worker_name}"
                            f"retry({retry_cnt}) request req({st.strftime('%M:%S.%f')}), "
                            f"res({et.strftime('%M:%S.%f')}), "
                            f"elapsed({(et-st).total_seconds()}), type:{req_map.request_type}, "
                            f"uri:{req_map.request_uri}, "
                            f"status:{response.status_code}, response:{response.text}, body:{req_map.request_body},"
                            f"partition:{req_map.commit_partition}, offset:{req_map.commit_offset}, cause:{errmsg}"
                        )
                        logger = logging.getLogger("retry")
                        logger.log(RETRY_REQUEST_LOG_LEVEL, msg)
            except requests.ConnectionError as e1:
                self.retry_request_uri_no_session_map(
                    worker_name, req_map=req_map, retry_cnt=retry_cnt + 1, errmsg=e1
                )
            except requests.Timeout as t1:
                self.retry_request_uri_no_session_map(
                    worker_name, req_map=req_map, retry_cnt=retry_cnt + 1, errmsg=t1
                )
            except requests.RequestException as e2:
                self.retry_request_uri_no_session_map(
                    worker_name, req_map=req_map, retry_cnt=retry_cnt + 1, errmsg=e2
                )
            except Exception as e3:
                self.retry_request_uri_no_session_map(
                    worker_name, req_map=req_map, retry_cnt=retry_cnt + 1, errmsg=e3
                )

        # fixme 개발 서버 slack 알림 제외 (Portfolio: Slack channel link removed)
        if APP_ENVIRONMENT == "PROD":
            if retry_cnt > HTTP_REQUEST_RETRY_LIMIT:
                msg = (
                    f"[{os.uname().nodename}]{worker_name}failed retry(until {retry_cnt-1}) "
                    f"type:{req_map.request_type},"
                    f"uri:{req_map.request_uri}, exception:{errmsg}, "
                    f"request_body:{req_map.request_body}"
                )
                logger = logging.getLogger("error")
                logger.log(logging.ERROR, msg)
                send_slack_notification(text=msg)

    def process_http_requests(self, request_items: List[RequestURIMap]):
        try:
            for item in request_items:
                if self.event.is_set():
                    break
                if item.request_type is not RequestType.NO_BEHAVIOR:
                    self.request_uri_no_session_map(
                        worker_name=self.name, req_map=item
                    )
        finally:
            self.update_offset_queue(request_items)

    def update_offset_queue(self, request_items: List[RequestURIMap]):
        # fixme list(requests_items) max 값을 가져옴
        _max_item = max(request_items, key=lambda x: x.commit_offset)
        partition = _max_item.commit_partition
        offset = _max_item.commit_offset

        # fixme offset_space 현재 파티션 해당 offset 값을 가져옴
        try:
            current_offset = self.offset_queue.get_nowait()
        except queue.Empty:
            current_offset = None

        if current_offset is None or offset > current_offset[1]:
            # fixme 현재 offset 이 큰 경우 offset_space 반영
            self.offset_queue.put_nowait((partition, offset))

        # fixme 디큐 카운트 반영
        self.de_queue_count_by_secs[0] += 1
        self.de_queue_count_each_thread[self.idx] += 1
        if len(self.de_queue_count) >= 1:
            self.de_queue_count[0] += 1
