from src.enums import BaseEnum


class PayloadType(BaseEnum):
    PRODUCT = "SCHEMA.PRODUCT_TABLE"

class OperationType(BaseEnum):
    INS = "I"
    UPD = "U"
    DEL = "D"

class RequestType(BaseEnum):
    ES_LOG_FILTERED_INS = "ES_LOG_FILTERED_INS__C"
    PRODUCT_INS = "PRODUCT_INS__C"
    NO_BEHAVIOR = "NO"
