"""
Filter functions for live product queue.
Portfolio version: Simplified filter for product data processing.
"""
from src.utils.structs import FilterResultMap
from src.utils.type import RequestType


def filter_case_of_product(payload: dict) -> FilterResultMap:
    """
    Portfolio version: Simplified filter for product data.
    Checks IS_DISPLAY flag from changed field.
    """
    filter_result_map = FilterResultMap()
    filter_result_map.filtered_method_name = filter_case_of_product.__name__

    try:
        # Get identity key from identity.NO
        identity_key = payload.get("identity", {}).get("NO")
        filter_result_map.identity_key = identity_key

        # Check IS_DISPLAY from changed field
        changed = payload.get("changed", {})
        is_display = changed.get("IS_DISPLAY")

        if is_display is True:
            # IS_DISPLAY is true, filter it
            filter_result_map.filtered_yn = "Y"
            filter_result_map.filtered_msg = "[changed]IS_DISPLAY(true) 필터"
            filter_result_map.request_type = RequestType.ES_LOG_FILTERED_INS
            filter_result_map.request_body = None
            return filter_result_map

        # If IS_DISPLAY is not true, allow processing
        filter_result_map.filtered_yn = "N"
        filter_result_map.filtered_msg = "[changed]IS_DISPLAY(false or None) 처리"
        filter_result_map.request_type = RequestType.PRODUCT_INS
        return filter_result_map

    except Exception as e1:
        raise Exception(e1)

