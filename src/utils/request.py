import asyncio
import json
import logging
import os
import traceback
from datetime import datetime, timedelta

import aiohttp
import requests

from src.configs.constants import (
    AIO_CLIENT_TIME_OUT,
    AIO_TCP_LIMIT_PER_HOST,
    HTTP_REQUEST_RETRY_LIMIT,
    HTTP_REQUEST_TIMEOUT,
    REQUEST_TIME_LOG_LEVEL,
    RETRY_REQUEST_LOG_LEVEL,
    base_uri,
)
from src.configs.env import APP_ENVIRONMENT
from src.uri_map import URI_MAP
from src.utils.slack import send_slack_notification, send_slack_alert
from src.utils.structs import FilterResultMap, RequestURIMap
from src.utils.type import RequestType


def get_uri(request_type: RequestType, identity_key: int) -> str:
    path_template = URI_MAP.get(request_type)
    if not path_template:
        raise ValueError(f"Unsupported request type: {request_type}")
    return f"{base_uri()}{path_template.format(identity_key=identity_key)}"


def make_request_map(
    request_type: RequestType, request_body: dict, identity: int, **kwargs
) -> RequestURIMap:
    if request_body is None:
        request_body = dict()

    request_body["processed_at"] = kwargs["extract_dt"]
    request_body["kafka_timestamp"] = datetime.fromtimestamp(
        kwargs["offset_occr_dt"] / 1000
    ).strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")

    try:
        # Portfolio: Convert DB timestamp with timezone offset (+09:00)
        db_dt = datetime.strptime(
            kwargs["dml_occr_dt"], "%Y-%m-%d %H:%M:%S.%f"
        ) + timedelta(hours=9)
        request_body["db_timestamp"] = db_dt.strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")
    except ValueError as e3:
        msg = f"request_uri parse error > db_timestamp:{e3}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    try:
        cdc_dt = datetime.strptime(kwargs["ogg_extrc_dt"], "%Y-%m-%dT%H:%M:%S.%f")
        request_body["cdc_extract_timestamp"] = cdc_dt.strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")
    except ValueError as e5:
        msg = f"request_uri parse error > cdc_extract_timestamp:{e5}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    _req_map = RequestURIMap()
    _req_map.identity_key = identity
    _req_map.request_uri = get_uri(request_type=request_type, identity_key=identity)
    _req_map.request_type = request_type
    _req_map.request_body = request_body
    return _req_map


def make_request_map_with_offset(
    filter_result: FilterResultMap, **kwargs
) -> RequestURIMap:
    # fixme setup request body
    try:
        if filter_result.request_body is None:
            filter_result.request_body = dict()

        filter_result.request_body["offset_no"] = kwargs["commit_offset"]
        filter_result.request_body["partition_no"] = kwargs["commit_partition"]
        filter_result.request_body["topic_nm"] = kwargs["topic_name"]

        # Portfolio: Record timestamps for processing tracking
        filter_result.request_body["processed_at"] = kwargs["extract_dt"]
        filter_result.request_body["kafka_timestamp"] = datetime.fromtimestamp(
            kwargs["offset_occr_dt"] / 1000
        ).strftime("%Y-%m-%dT%H:%M:%S.%f")

        filter_result.request_body["op_type"] = filter_result.op_type.value
        filter_result.request_body["filtered_yn"] = filter_result.filtered_yn
        filter_result.request_body["filtered_msg"] = filter_result.filtered_msg
    except KeyError as e1:
        msg = f"parse key error:{e1}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    try:
        # Portfolio: Convert DB timestamp with timezone offset (+09:00)
        db_dt = datetime.strptime(
            kwargs["dml_occr_dt"], "%Y-%m-%d %H:%M:%S.%f"
        ) + timedelta(hours=9)
        filter_result.request_body["db_timestamp"] = db_dt.strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )
    except ValueError as e2:
        msg = f"parse error db_timestamp:{e2}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    try:
        cdc_dt = datetime.strptime(kwargs["ogg_extrc_dt"], "%Y-%m-%dT%H:%M:%S.%f")
        filter_result.request_body["cdc_extract_timestamp"] = cdc_dt.strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )
    except ValueError as e3:
        msg = f"parse error cdc_extract_timestamp:{e3}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    _req_map = RequestURIMap()
    _req_map.identity_key = filter_result.identity_key
    _req_map.request_uri = get_uri(
        request_type=filter_result.request_type, identity_key=filter_result.identity_key
    )
    _req_map.request_type = filter_result.request_type
    _req_map.request_body = filter_result.request_body
    _req_map.commit_offset = kwargs["commit_offset"]
    _req_map.commit_partition = kwargs["commit_partition"]
    return _req_map


def retry_request_uri_session_map(
    worker_name: str, req_map: RequestURIMap, retry_cnt: int, errmsg
):
    if retry_cnt <= HTTP_REQUEST_RETRY_LIMIT:
        headers = {"Content-Type": "application/json", "charset": "utf-8"}
        try:
            with requests.session() as session:
                st = datetime.now()
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
                    f"elapsed({(et-st).total_seconds()}), type:{req_map.request_type}, uri:{req_map.request_uri}, "
                    f"status:{response.status_code}, response:{response.text}, body:{req_map.request_body},"
                    f"partition:{req_map.commit_partition}, offset:{req_map.commit_offset}, cause:{errmsg}"
                )
                logger = logging.getLogger("retry")
                logger.log(RETRY_REQUEST_LOG_LEVEL, msg)
        except requests.ConnectionError as e1:
            retry_request_uri_session_map(
                worker_name, req_map=req_map, retry_cnt=retry_cnt + 1, errmsg=e1
            )
        except requests.Timeout as t1:
            retry_request_uri_session_map(
                worker_name, req_map=req_map, retry_cnt=retry_cnt + 1, errmsg=t1
            )
        except requests.RequestException as e2:
            retry_request_uri_session_map(
                worker_name, req_map=req_map, retry_cnt=retry_cnt + 1, errmsg=e2
            )

    # fixme 개발 서버 slack 알림 제외 (Portfolio: Slack channel link removed)
    if APP_ENVIRONMENT == "PROD":
        if retry_cnt > 10:
            msg = (
                f"[{os.uname().nodename}]{worker_name}failed retry(until {retry_cnt-1}) "
                f"type:{req_map.request_type},"
                f"uri:{req_map.request_uri}, exception:{errmsg}, "
                f"request_body:{req_map.request_body}"
            )
            logger = logging.getLogger("error")
            logger.log(logging.ERROR, msg)
            send_slack_notification(text=msg)


def request_uri_no_session_map(worker_name: str, req_map: RequestURIMap):
    try:
        headers = {"Content-Type": "application/json", "charset": "utf-8"}

        with requests.session() as session:
            st = datetime.now()
            req_map.request_body.update(
                {"request_timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")}
            )

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
        retry_request_uri_session_map(
            worker_name=worker_name, req_map=req_map, retry_cnt=1, errmsg=e1
        )
    return NotImplemented


def request_uri_session_map(
    worker_name: str, session: requests.Session, req_map: RequestURIMap
):
    try:
        headers = {"Content-Type": "application/json", "charset": "utf-8"}

        st = datetime.now()
        response = None
        if "__C" in str(req_map.request_type):
            response = session.post(
                req_map.request_uri, headers=headers, json=req_map.request_body
            )
        elif "__U" in str(req_map.request_type):
            response = session.put(
                req_map.request_uri, headers=headers, json=req_map.request_body
            )
        elif "__D" in str(req_map.request_type):
            response = session.delete(req_map.request_uri, json=req_map.request_body)
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
    except Exception as e1:
        retry_request_uri_session_map(
            worker_name=worker_name, req_map=req_map, retry_cnt=1, errmsg=e1
        )
    return NotImplemented


def request_uri_map(req_map_list: list[RequestURIMap]):
    headers = {"Content-Type": "application/json", "charset": "utf-8"}
    with requests.session() as sess:
        for req_map in req_map_list:
            try:
                st = datetime.now()
                if "__C" in str(req_map.request_type):
                    response = sess.post(
                        req_map.request_uri, headers=headers, json=req_map.request_body
                    )
                elif "__U" in str(req_map.request_type):
                    response = sess.put(
                        req_map.request_uri, headers=headers, json=req_map.request_body
                    )
                elif "__D" in str(req_map.request_type):
                    response = sess.delete(
                        req_map.request_uri, json=req_map.request_body
                    )

                et = datetime.now()
                msg = (
                    f"req({st.strftime('%M:%S.%f')}), res({et.strftime('%M:%S.%f')}), "
                    f"elapsed({(et-st).total_seconds()}), type:{req_map.request_type}, uri:{req_map.request_uri}, "
                    f"status:{response.status_code}, response:{response.text}, body:{req_map.request_body}"
                )

                logger = logging.getLogger("request")
                logger.log(logging.INFO, msg)
            except requests.exceptions.ConnectionError as e1:
                msg = (
                    f"type:{req_map.request_type}, uri:{req_map.request_uri}, exception:{e1}, "
                    f"request_body:{req_map.request_body}"
                )
                _logger = logging.getLogger("error")
                _logger.log(logging.ERROR, msg)
                send_slack_notification(text=msg)
            except requests.exceptions.RequestException as e2:
                msg = (
                    f"type:{req_map.request_type}, uri:{req_map.request_uri}, exception:{e2}, "
                    f"request_body:{req_map.request_body}"
                )
                _logger = logging.getLogger("error")
                _logger.log(logging.ERROR, msg)
                send_slack_notification(text=msg)

    return NotImplemented


async def async_fetch_url(session: aiohttp.ClientSession, req_map: RequestURIMap):
    headers = {"Content-Type": "application/json", "charset": "utf-8"}

    try:
        st = datetime.now()
        if "__C" in str(req_map.request_type):
            async with session.post(
                req_map.request_uri, headers=headers, json=req_map.request_body
            ) as resp:
                et = datetime.now()
                msg = (
                    f"req({st.strftime('%M:%S.%f')}), res({et.strftime('%M:%S.%f')}), "
                    f"elapsed({(et-st).total_seconds()}), type:{req_map.request_type}, uri:{req_map.request_uri}, "
                    f"status:{resp.status}, body:{req_map.request_body}"
                )
                logger = logging.getLogger("request")
                logger.log(REQUEST_TIME_LOG_LEVEL, msg)
                return resp.status
        elif "__U" in str(req_map.request_type):
            async with session.put(
                req_map.request_uri, headers=headers, json=req_map.request_body
            ) as resp:
                et = datetime.now()
                msg = (
                    f"req({st.strftime('%M:%S.%f')}), res({et.strftime('%M:%S.%f')}), "
                    f"elapsed({(et-st).total_seconds()}), type:{req_map.request_type}, uri:{req_map.request_uri}, "
                    f"status:{resp.status}, body:{req_map.request_body}"
                )
                logger = logging.getLogger("request")
                logger.log(REQUEST_TIME_LOG_LEVEL, msg)
                return resp.status
        elif "__D" in str(req_map.request_type):
            async with session.delete(
                req_map.request_uri, headers=headers, json=req_map.request_body
            ) as resp:
                et = datetime.now()
                msg = (
                    f"req({st.strftime('%M:%S.%f')}), res({et.strftime('%M:%S.%f')}), "
                    f"elapsed({(et-st).total_seconds()}), type:{req_map.request_type}, uri:{req_map.request_uri}, "
                    f"status:{resp.status}, body:{req_map.request_body}"
                )
                logger = logging.getLogger("request")
                logger.log(REQUEST_TIME_LOG_LEVEL, msg)
                return resp.status
    except aiohttp.ClientError as e:
        msg = (
            f"type:{req_map.request_type}, uri:{req_map.request_uri}, exception:{e}, "
            f"request_body:{req_map.request_body}"
        )
        _logger = logging.getLogger("error")
        _logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)


async def async_task_request_uri_queue(req_map_list: list[RequestURIMap]):
    try:
        tasks = []
        connector = aiohttp.TCPConnector(
            ssl=False, limit_per_host=AIO_TCP_LIMIT_PER_HOST
        )
        timeout = aiohttp.ClientTimeout(total=AIO_CLIENT_TIME_OUT)
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            for req_map in req_map_list:
                if req_map.request_type is not RequestType.NO_BEHAVIOR:
                    task = asyncio.create_task(
                        async_fetch_url(session=session, req_map=req_map)
                    )
                    tasks.append(task)
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e1:
        msg = f"async_request_uri_map:{e1}, traceback:{traceback.format_exc()}"
        _logger = logging.getLogger("error")
        _logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)
    return NotImplemented


async def async_task_request_uri_map(req_map_list: list[RequestURIMap]):
    try:
        tasks = []
        connector = aiohttp.TCPConnector(
            ssl=False, limit_per_host=AIO_TCP_LIMIT_PER_HOST
        )
        timeout = aiohttp.ClientTimeout(total=AIO_CLIENT_TIME_OUT)
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            for req_map in req_map_list:
                task = asyncio.create_task(
                    async_fetch_url(session=session, req_map=req_map)
                )
                tasks.append(task)
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e1:
        msg = f"async_request_uri_map:{e1}, traceback:{traceback.format_exc()}"
        _logger = logging.getLogger("error")
        _logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)
    return NotImplemented


async def async_request_uri_map_with_session(
    session: aiohttp.ClientSession, req_map_list: list[RequestURIMap]
):
    for req_map in req_map_list:
        try:
            st = datetime.now()
            task = async_fetch_url(session=session, req_map=req_map)
            status_code = await task
            et = datetime.now()
            msg = (
                f"req({st.strftime('%M:%S.%f')}), res({et.strftime('%M:%S.%f')}), "
                f"elapsed({(et-st).total_seconds()}), type:{req_map.request_type}, uri:{req_map.request_uri}, "
                f"status:{status_code}, body:{req_map.request_body}"
            )

            logger = logging.getLogger("info")
            logger.log(logging.INFO, msg)
        except requests.exceptions.ConnectionError as e1:
            msg = (
                f"type:{req_map.request_type}, uri:{req_map.request_uri}, exception:{e1}, "
                f"request_body:{req_map.request_body}"
            )
            _logger = logging.getLogger("error")
            _logger.log(logging.ERROR, msg)
            send_slack_notification(text=msg)
        except requests.exceptions.RequestException as e2:
            msg = (
                f"type:{req_map.request_type}, uri:{req_map.request_uri}, exception:{e2}, "
                f"request_body:{req_map.request_body}"
            )
            _logger = logging.getLogger("error")
            _logger.log(logging.ERROR, msg)
            send_slack_notification(text=msg)

    return NotImplemented


def request_uri(request_type: RequestType, request_body: dict, identity: int, **kwargs):
    if request_body is None:
        request_body = dict()

    # Portfolio: Record timestamps for processing tracking
    request_body["processed_at"] = kwargs["extract_dt"]
    request_body["kafka_timestamp"] = datetime.fromtimestamp(
        kwargs["offset_occr_dt"] / 1000
    ).strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")

    try:
        # Portfolio: Convert DB timestamp with timezone offset (+09:00)
        db_dt = datetime.strptime(
            kwargs["dml_occr_dt"], "%Y-%m-%d %H:%M:%S.%f"
        ) + timedelta(hours=9)
        request_body["db_timestamp"] = db_dt.strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")
    except ValueError as e3:
        msg = f"request_uri parse error > db_timestamp:{e3}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    try:
        cdc_dt = datetime.strptime(kwargs["ogg_extrc_dt"], "%Y-%m-%dT%H:%M:%S.%f")
        request_body["cdc_extract_timestamp"] = cdc_dt.strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")
    except ValueError as e5:
        msg = f"request_uri parse error > cdc_extract_timestamp:{e5}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    headers = {"Content-Type": "application/json"}
    url = get_uri(request_type=request_type, identity_key=identity)

    logger = logging.getLogger("info")
    st = datetime.now()

    try:
        with requests.Session() as sess:
            if "__C" in str(request_type):
                response = sess.post(url, headers=headers, json=request_body)
            elif "__U" in str(request_type):
                response = sess.put(url, headers=headers, json=request_body)
            elif "__D" in str(request_type):
                response = sess.delete(url, json=request_body)

        et = datetime.now()
        msg = (
            f"req({st.strftime('%M:%S.%f')}), res({et.strftime('%M:%S.%f')}), "
            f"elapsed({(et-st).total_seconds()}), type:{request_type}, uri:{url},"
            f"status:{response.status_code}, response:{response.text}, body:{request_body}"
        )
        logger.log(logging.INFO, msg)
    except requests.exceptions.ConnectionError as e1:
        msg = f"type:{request_type}, uri:{url}, exception:{e1}, request_body:{json}"
        raise requests.exceptions.ConnectionError(e1, identity, msg)
    except requests.exceptions.RequestException as e2:
        # 여기서 Retry 처리를 해준다.
        msg = f"type:{request_type}, uri:{url}, exception:{e2}, request_body:{json}"
        raise requests.exceptions.RequestException(e2, identity, msg)

    return NotImplemented


async def async_http_request(
    session: aiohttp.ClientSession,
    request_type: RequestType,
    url: str,
    request_body: dict,
):
    headers = {"Content-Type": "application/json"}
    if "__C" in str(request_type):
        async with session.post(url, headers=headers, json=request_body) as resp:
            return resp.status
    elif "__U" in str(request_type):
        async with session.put(url, headers=headers, json=request_body) as resp:
            return resp.status
    elif "__D" in str(request_type):
        async with session.delete(url, headers=headers, json=request_body) as resp:
            return resp.status


async def async_request_uri(
    request_type: RequestType, request_body: dict, identity: int, **kwargs
):
    if request_body is None:
        request_body = dict()

    # Portfolio: Record timestamps for processing tracking
    request_body["processed_at"] = kwargs["extract_dt"]
    request_body["kafka_timestamp"] = datetime.fromtimestamp(
        kwargs["offset_occr_dt"] / 1000
    ).strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")

    try:
        # Portfolio: Convert DB timestamp with timezone offset (+09:00)
        db_dt = datetime.strptime(
            kwargs["dml_occr_dt"], "%Y-%m-%d %H:%M:%S.%f"
        ) + timedelta(hours=9)
        request_body["db_timestamp"] = db_dt.strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")
    except ValueError as e3:
        msg = f"request_uri parse error > db_timestamp:{e3}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    try:
        cdc_dt = datetime.strptime(kwargs["ogg_extrc_dt"], "%Y-%m-%dT%H:%M:%S.%f")
        request_body["cdc_extract_timestamp"] = cdc_dt.strftime("%Y-%m-%dT%H:%M:%S.%f+09:00")
    except ValueError as e5:
        msg = f"request_uri parse error > cdc_extract_timestamp:{e5}, traceback:{traceback.format_exc()}"
        logger = logging.getLogger("error")
        logger.log(logging.ERROR, msg)
        send_slack_notification(text=msg)

    try:
        async with aiohttp.ClientSession() as sess:
            req_st = datetime.now()
            url = get_uri(request_type=request_type, identity_key=identity)
            task = async_http_request(
                session=sess,
                request_type=request_type,
                url=url,
                request_body=request_body,
            )
            status_code = await task
            req_et = datetime.now()
            msg = (
                f"req({req_st.strftime('%M:%S.%f')}), res({req_et.strftime('%M:%S.%f')}), "
                f"elapsed({(req_et-req_st).total_seconds()}), type:{request_type}, uri:{url}, "
                f"status:{status_code}, body:{request_body}"
            )
            logger = logging.getLogger("info")
            logger.log(logging.INFO, msg)

    except requests.exceptions.ConnectionError as e1:
        msg = f"type:{request_type}, uri:{url}, exception:{e1}, request_body:{json}"
        raise requests.exceptions.ConnectionError(e1, identity, msg)
    except requests.exceptions.RequestException as e2:
        # 여기서 Retry 처리를 해준다.
        msg = f"type:{request_type}, uri:{url}, exception:{e2}, request_body:{json}"
        raise requests.exceptions.RequestException(e2, identity, msg)
