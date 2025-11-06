"""
Test cases for live_prd_que filter functions.
Portfolio version: Tests for product data filtering logic.

Note: Test data uses generic Oracle Golden Gate CDC message format.
The column names match the filter expectations, but values are generalized.
"""
from src.filters.filter_product import filter_case_of_product
from src.utils.payload import parse_to_payload
from src.utils.structs import FilterResultMap
from src.utils.type import RequestType


def test_filter_case_01():
    """Test filter with IS_DISPLAY=true should be filtered."""
    json_str = """
    {
        "table": "SCHEMA.PRODUCT_TABLE",
        "pos": "00000000000000000001",
        "tokens": {},
        "changed": {
            "IS_DISPLAY": true
        },
        "identity": {
            "NO": 1001
        }
    }
    """
    payload = parse_to_payload(json_str)
    filter_result: FilterResultMap = filter_case_of_product(payload=payload)
    assert filter_result.request_type == RequestType.ES_LOG_FILTERED_INS
    assert filter_result.request_body is None
    assert filter_result.identity_key == 1001
    assert filter_result.filtered_yn == "Y"
    print(filter_result.filtered_msg)

