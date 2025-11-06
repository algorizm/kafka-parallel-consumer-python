from typing import Optional

from src.utils.type import OperationType, PayloadType


def get_payload_type(
    payload: dict,
) -> tuple[Optional[PayloadType], Optional[OperationType]]:
    """
    Payload Enum 타입 처리
    Portfolio version: Simplified to only handle PRODUCT payload type.
    """
    pl_type = op_type = None
    try:
        # Portfolio: Check for product table (generalized schema name)
        table_name = payload.get("table", "")
        
        # Check if it's a product table (generalized check)
        if "PRODUCT" in table_name.upper() or "PRD" in table_name.upper():
            pl_type = PayloadType.PRODUCT

        # Get operation type
        op_type_str = payload.get("op_type", "")
        if op_type_str == "I":
            op_type = OperationType.INS
        elif op_type_str == "U":
            op_type = OperationType.UPD
        elif op_type_str == "D":
            op_type = OperationType.DEL
    except KeyError as e:
        raise KeyError(f"get_payload_type:{e}")

    return pl_type, op_type
