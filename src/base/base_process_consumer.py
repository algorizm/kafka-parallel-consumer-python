import logging
import multiprocessing
import queue
import threading
import time
import traceback
from datetime import datetime
from typing import Optional

from confluent_kafka import Consumer, TopicPartition

from src.base.base_process_worker import SendHttpWorker
from src.base.concurrent_logger import BatchQueueLog
from src.base.sched_timer import Scheduler
from src.configs.constants import (
    CHECK_END_INTERVAL_SECONDS,
    COMMIT_INTERVAL_SECONDS,
    COMMIT_OFFSET_LOG_LEVEL,
    EACH_REQUEST_THREAD_LOG_LEVEL,
    MESSAGE_COUNT_INTERVAL_SECONDS,
    MESSAGE_COUNT_LOG_LEVEL,
)
from src.utils.payload import apply_filter, parse_to_payload
from src.utils.request import make_request_map_with_offset
from src.utils.slack import send_slack_notification
from src.utils.structs import RequestURIMap

# https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html#pythonclient-consumer
# https://docs.python.org/ko/3/library/sched.html#sched.scheduler


class ConsumerMain:
    def __init__(
        self,
        config: dict,
        topic_name: str,
        logger_cls: BatchQueueLog,
        event: multiprocessing.Event,
        queue_max_size: int = -1,
    ):
        self.topic = topic_name
        self.config = config
        self.logger = logger_cls
        self.process_event = event
        self.thread_event = threading.Event()

        # fixme current offset info.
        self.offset = None
        self.partition = None
        self.key = None
        self.payload = None
        self.consumer: Optional[Consumer] = None

        # fixme queue info.
        self.is_record_total = False
        self.cosume_count = 0
        self.in_queue_count = 0
        if self.is_record_total:
            self.de_queue_count = [0]
        else:
            self.de_queue_count = []

        self.consume_count_by_secs = 0
        self.in_queue_count_by_secs = 0
        self.de_queue_count_by_secs = [0]
        self.de_queue_count_each_thread = [0]

        self.process_id = multiprocessing.current_process().pid
        self.request_queue = queue.Queue(maxsize=queue_max_size)
        self.offset_queue = queue.SimpleQueue()
        self.request_threads = list()

        self.schedule_commit: Optional[Scheduler] = None
        self.schedule_end_commit: Optional[Scheduler] = None

        # # fixme 자식 프로세스 SIGINT 무시 (메인 프로세스 SIGNIT 신호만(KeyboardInterrupt) 받아서 처리)
        # signal.signal(signal.SIGINT, self._signal_handler)
        # fixme 자식 프로세스 SIGTERM 신호 처리
        # signal.signal(signal.SIGTERM, self._signal_handler)

    def __del__(self):
        self.request_queue = None
        self.offset_queue = None
        self.request_threads = None

    def _signal_handler(self, signum, _frame):
        self.logger.log(
            logging.INFO,
            f"Subprocess {self.process_id} received termination signal ({signum}), shutting down.",
        )
        self.process_event.set()

    def wait_done(self):
        # fixme 모든 스레드 및 리소스 safe shutdown
        try:
            while not self.request_queue.empty():
                try:
                    self.request_queue.get_nowait()
                except queue.Empty:
                    break

            for req_thread in self.request_threads:
                req_thread.queue.put(None)
                req_thread.event.set()

            dispose_count = len(self.request_threads)
            self.logger.log(
                logging.INFO,
                f"[{self.process_id}]Terminated all http_worker threads ({dispose_count})",
            )
        finally:
            if self.schedule_commit is not None:
                self.schedule_commit.cancel()
            if self.schedule_end_commit is not None:
                self.schedule_end_commit.cancel()
            self.offset_commit_close()
            # Log 스레드 종료
            self.logger.wait_done()

    def start_concurrent_request(self, number: int = 1):
        # fixme 병렬 요청 스레드 시작
        started_count = 0
        for num in range(1, number + 1):
            self.de_queue_count_each_thread.append(0)
            req_thread = SendHttpWorker(
                name=f"[{self.process_id},http-worker-{num}]",
                event=self.thread_event,
                message_queue=self.request_queue,
                offset_queue=self.offset_queue,
                idx=num,
                main_process_id=self.process_id,
                de_queue_count=self.de_queue_count,
                de_queue_count_by_secs=self.de_queue_count_by_secs,
                de_queue_count_each_thread=self.de_queue_count_each_thread,
            )
            self.request_threads.append(req_thread)
            req_thread.start()
            started_count += 1
        self.logger.log(
            logging.INFO,
            f"[{self.process_id}]Started all http-worker threads ({started_count})",
        )

    def __logging_message_count(self, thread_id: int):
        try:
            # fixme 0 으로 초기화 배열 길이 보다 긴 경우 체크
            if len(self.de_queue_count_each_thread) > 1:
                _total_message = f"[{thread_id}][{self.partition}]"
                if self.is_record_total:
                    _total_message = (
                        f"{_total_message}consume(total):{self.cosume_count}, "
                        f"enqueue(total):{self.in_queue_count}, "
                        f"dequeue(total):{self.de_queue_count[0]}, "
                        f"ramain(total):{self.in_queue_count - self.de_queue_count[0]}, "
                    )

                _consume_message = (
                    f"{_total_message}consume(per):{self.consume_count_by_secs}, "
                    f"{_total_message}dequeue(per):{self.de_queue_count_by_secs[0]}, "
                    f"qsize(req):{self.request_queue.qsize()}, "
                    f"qsize(log):{self.logger.get_qsize()}"
                )

                _thread_message = f"t1:{self.de_queue_count_each_thread[1]}, "
                for num in range(2, len(self.de_queue_count_each_thread) - 1):
                    _thread_message = f"{_thread_message}t{num}:{self.de_queue_count_each_thread[num]}, "
                _thread_message = (
                    f"{_thread_message}t{len(self.de_queue_count_each_thread)-1}:"
                    f"{self.de_queue_count_each_thread[len(self.de_queue_count_each_thread)-1]}"
                )
                self.logger.log(EACH_REQUEST_THREAD_LOG_LEVEL, _thread_message)
                self.logger.log(MESSAGE_COUNT_LOG_LEVEL, _consume_message)

            # fixme initialize per count
            self.consume_count_by_secs = 0
            self.in_queue_count_by_secs = 0
            self.de_queue_count_by_secs[0] = 0
            for i, _ in enumerate(self.de_queue_count_each_thread):
                self.de_queue_count_each_thread[i] = 0
        finally:
            self.__on_timer_logging_message_count()

    def __schedule_commit(self, thread_id: int):
        try:
            if self.consumer is None:
                return

            # fixme committed offset for each partition
            while not self.offset_queue.empty():
                if self.process_event.is_set():
                    return

                _partition, _offset = self.offset_queue.get()
                try:
                    if self.consumer is not None:
                        self.consumer.commit(
                            offsets=[
                                TopicPartition(
                                    topic=self.topic,
                                    partition=_partition,
                                    offset=_offset + 1,
                                )
                            ],
                            asynchronous=True,
                        )
                        self.logger.log(
                            COMMIT_OFFSET_LOG_LEVEL,
                            f"[{thread_id}]Offset commit handing by the schedule_commit -> partition:{_partition}, "
                            f"offset:{_offset+1}",
                        )
                except RuntimeError:
                    self.logger.log(
                        logging.INFO,
                        "[__schedule_commit]Consumer is None, skipping commit.",
                    )
        finally:
            self.__on_timer_schedule_commit()

    def __schedule_end_commit(self, thread_id: int):
        # fixme 현재 오프셋이 브로커 end offset 보다 적은 경우 커밋 처리
        #  요청 스레드 응답이 지연 된 경우 오프셋 값이 이전 값으로 돌아가는 현상 방지(1분 단위 체크)
        try:
            if self.offset_queue.empty() and self.request_queue.qsize() == 0:
                if self.partition is not None and self.offset is not None:
                    if self.consumer is not None:
                        if self.process_event.is_set():
                            return

                        self.consumer.commit(asynchronous=True)
                        self.logger.log(
                            COMMIT_OFFSET_LOG_LEVEL,
                            f"[{thread_id}]Offset commit hading by schedule_end_commit -> partition:{self.partition}, "
                            f"offset:{self.offset+1}",
                        )
        except Exception as e:
            msg = (
                f"failed __schedule_end_commit:{e}, traceback:{traceback.format_exc()}"
            )
            self.logger.log(logging.ERROR, msg)
            send_slack_notification(text=msg)
        finally:
            self.__on_timer_schedule_end_commit()

    def __on_timer_logging_message_count(self):
        if self.process_event.is_set():
            return
        Scheduler(
            name="logging_message_count",
            interval=MESSAGE_COUNT_INTERVAL_SECONDS,
            function=self.__logging_message_count,
            args=(self.process_id,),
        ).start()

    def __on_timer_schedule_commit(self):
        if self.process_event.is_set():
            return
        self.schedule_commit = Scheduler(
            name="schedule_commit",
            interval=COMMIT_INTERVAL_SECONDS,
            function=self.__schedule_commit,
            args=(self.process_id,),
        ).start()

    def __on_timer_schedule_end_commit(self):
        if self.process_event.is_set():
            return
        self.schedule_end_commit = Scheduler(
            name="schedule_end_commit",
            interval=CHECK_END_INTERVAL_SECONDS,
            function=self.__schedule_end_commit,
            args=(self.process_id,),
        ).start()

    def offset_commit_close(self):
        try:
            while not self.offset_queue.empty():
                if self.process_event.is_set():
                    break

                _partition, _offset = self.offset_queue.get_nowait()
                if self.consumer is not None:
                    try:
                        self.consumer.commit(
                            offsets=[
                                TopicPartition(
                                    topic=self.topic,
                                    partition=_partition,
                                    offset=_offset,
                                )
                            ],
                            asynchronous=True,
                        )
                        self.logger.log(
                            COMMIT_OFFSET_LOG_LEVEL,
                            f"[{self.process_id}]commit offset by offset_commit_close -> "
                            f"partition:{_partition}, offset:{_offset}",
                        )
                    except RuntimeError:
                        self.logger.log(
                            logging.INFO,
                            f"[{self.process_id}]Consumer is None in the offset_commit_close function, "
                            f"skipping commit.",
                        )
        finally:
            if self.consumer:
                self.consumer.close()

    def consume(self, partition_no: int = None):
        try:
            self.consumer = Consumer(self.config)
            self.consumer.subscribe([self.topic])

            self.__on_timer_logging_message_count()
            self.__on_timer_schedule_commit()
            self.__on_timer_schedule_end_commit()
            self.logger.log(
                COMMIT_OFFSET_LOG_LEVEL,
                f"[{self.process_id}]Settings the event timer for the commit scheduler",
            )

            if partition_no is not None and partition_no >= 0:
                self.consumer.assign(
                    [TopicPartition(topic=self.topic, partition=partition_no)]
                )

            first_poll = True
            while not self.process_event.is_set():
                msg = self.consumer.poll(0.1)
                if msg is None:
                    continue

                if self.process_event.is_set():
                    break

                if msg.error():
                    error = msg.error()
                    error_code = msg.error().code()

                    # fixme KafkaError._PARTITION_EOF (protected member) 이므로 직접 접근할 수 없음
                    #  대신 코드값 -191 을 직접 사용 하여 비교 처리
                    if error_code == -191:
                        msg_text = f"{msg.topic()} {msg.partition()} reached end at offset {msg.offset()}"
                        self.logger.log(logging.ERROR, msg_text)
                        send_slack_notification(text=msg_text)
                    else:
                        msg_text = f"KafkaError msg error: {error}"
                        self.logger.log(logging.ERROR, msg_text)
                        send_slack_notification(text=msg_text)

                    continue

                # fixme consume timestamp
                extract_dt = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")

                self.partition = msg.partition()
                self.offset = msg.offset()
                self.key = msg.key()

                if first_poll:
                    self.logger.log(
                        logging.INFO,
                        f"[{self.process_id}]Started consuming partition {self.partition}.",
                    )
                    first_poll = False

                filter_map = []
                try:
                    # fixme count consume
                    self.consume_count_by_secs += 1
                    if self.is_record_total:
                        self.cosume_count += 1

                    # noinspection PyArgumentList
                    raw = msg.value().decode("utf-8")
                    self.payload = parse_to_payload(raw=raw) or {}

                    # fixme apply_filter 호출 전에 self.payload 검증
                    if isinstance(self.payload, dict):
                        filter_map = apply_filter(
                            payload=self.payload, key=self.key.decode("utf-8")
                        )
                except Exception as ie:
                    # fixme payload 포맷 에러 시 해당 오프셋 바로 커밋
                    self.consumer.commit(asynchronous=True)
                    msg = (
                        f"payload error:{ie}, traceback:{traceback.format_exc()},"
                        f"payload:{self.payload}, "
                        f"partition:{self.partition}, offset:{self.offset}"
                    )
                    self.logger.log(logging.ERROR, msg)
                    send_slack_notification(text=msg)
                    continue

                if len(filter_map) > 0:
                    _req_uri_map_list: list[RequestURIMap] = []
                    for _filter_result in filter_map:
                        # fixme: _filter_result = (request_type, identity, request_body)
                        try:
                            # fixme 필터링 메시지 ES 로그 저장
                            _req_map: RequestURIMap = make_request_map_with_offset(
                                filter_result=_filter_result,
                                extract_dt=extract_dt,
                                offset_occr_dt=msg.timestamp()[1],
                                dml_occr_dt=self.payload.get("op_ts"),
                                ogg_extrc_dt=self.payload.get("current_ts"),
                                # Portfolio: Parameter names kept for backward compatibility,
                                # but field names in request_body are generalized
                                topic_name=self.topic,
                                commit_offset=self.offset,
                                commit_partition=self.partition,
                            )
                            _req_uri_map_list.append(_req_map)

                        except Exception as ie1:
                            # fixme 로깅 하고 계속 수행
                            msg = f"make_request_map:{ie1}, traceback:{traceback.format_exc()}"
                            self.logger.log(logging.ERROR, msg)
                            send_slack_notification(text=msg)
                            continue

                    # fixme Request 리스트 생성 이후 요청 처리
                    if len(_req_uri_map_list) > 0:
                        # fixme 블로킹 함수 put, get 처리 하는 동안 다른 스레드 큐 대기 상태
                        while not self.process_event.is_set():
                            try:
                                # fixme 메시지큐 풀이 난 경우 대기 시간이 너무 짧으면 오버헤드 발생
                                self.request_queue.put(_req_uri_map_list, timeout=1)
                                self.in_queue_count_by_secs += 1
                                if self.is_record_total:
                                    self.in_queue_count += 1
                                break
                            except queue.Full:
                                if self.process_event.is_set():
                                    break
                                time.sleep(0.1)
        except Exception as e1:
            msg = f"Shutting down the consumer:{e1}, traceback:{traceback.format_exc()}"
            self.logger.log(logging.ERROR, msg)
            send_slack_notification(text=msg)
        finally:
            self.logger.log(
                logging.INFO,
                f"[{self.process_id}]Called the wait_done function when shutting down the consumer",
            )
            self.wait_done()
