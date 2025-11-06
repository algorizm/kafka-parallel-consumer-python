"""
URI mapping for request types.
Portfolio version: Simplified URI templates for product consumer.
"""
from src.utils.type import RequestType

URI_MAP: dict[RequestType, str] = {
    RequestType.ES_LOG_FILTERED_INS: "/es-log/filtered",
    RequestType.PRODUCT_INS: "/product/{identity_key}",
    RequestType.NO_BEHAVIOR: "/no-behavior",
}

