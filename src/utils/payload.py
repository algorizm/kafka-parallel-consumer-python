import json
import re
from typing import Union

from src.filters.filter_product import filter_case_of_product
from src.utils.common import get_payload_type
from src.utils.structs import FilterResultMap
from src.utils.type import PayloadType


def remove_problem_fields(json_str: str) -> str:
    """Remove problematic fields from JSON string."""
    # Portfolio: Example schema name - replace with actual schema in production
    if "DP_LIVE_PRD" in json_str:
        if "DLV_INFO_JSON" in json_str:
            replace_str = re.sub(
                r'"DLV_INFO_JSON": (null|[^}]*.[^,]).',
                "",
                json_str,
                flags=re.MULTILINE | re.DOTALL,
            )
            return replace_str
    return json_str


def parse_to_payload(raw: str) -> dict:
    try:
        cleaned_json = remove_problem_fields(json_str=raw)
        payload = json.loads(cleaned_json)
    except json.JSONDecodeError:
        raise Exception(json.JSONDecodeError)
    return payload


def apply_filter(
    payload: dict, key: Union[str, bytes, None] = None
) -> list[FilterResultMap]:
    """RequestType list 형태로 리턴"""
    payload_type, op_type = get_payload_type(payload=payload)
    filter_result_map: list[FilterResultMap] = list()

    # fixme 필터 리스트 추가
    if payload_type == PayloadType.PRODUCT:
        # fixme live_prd_que
        filter_map: FilterResultMap = filter_case_of_product(payload=payload)
        filter_result_map.append(filter_map)

    return filter_result_map
