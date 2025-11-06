from dataclasses import dataclass, field

from src.utils.type import OperationType, RequestType


def default_request_body():
    """
    Portfolio version: Generalize timestamp field names.
    - processed_at: When the consumer processed the message
    - kafka_timestamp: Kafka message timestamp
    - db_timestamp: Database DML operation timestamp
    - cdc_extract_timestamp: CDC tool extraction timestamp
    """
    return {
        "processed_at": None,
        "kafka_timestamp": None,
        "db_timestamp": None,
        "cdc_extract_timestamp": None,
    }


@dataclass
class RequestURIMap:
    _identity_key: int = field(init=False)
    _request_uri: str = field(init=False)
    _request_type: RequestType = field(init=False)
    _request_body: dict = field(init=False)
    _commit_offset: int | None = field(init=False)
    _commit_partition: int | None = field(init=False)

    @property
    def identity_key(self):
        return self._identity_key

    @property
    def request_uri(self):
        return self._request_uri

    @property
    def request_type(self):
        return self._request_type

    @property
    def request_body(self):
        return self._request_body

    @property
    def commit_offset(self):
        return self._commit_offset

    @property
    def commit_partition(self):
        return self._commit_partition

    @identity_key.setter
    def identity_key(self, value):
        self._identity_key = value

    @request_uri.setter
    def request_uri(self, value):
        self._request_uri = value

    @request_type.setter
    def request_type(self, value):
        self._request_type = value

    @request_body.setter
    def request_body(self, value):
        self._request_body = value

    @commit_offset.setter
    def commit_offset(self, value):
        self._commit_offset = value

    @commit_partition.setter
    def commit_partition(self, value):
        self._commit_partition = value


@dataclass
class FilterResultMap:
    _operation_type: OperationType = field(init=False)
    _request_type: RequestType = field(init=False)
    _identity_key: int = 0
    _request_body: dict = None
    _filtered_yn: str = "N"
    _filtered_msg: str = ""
    _full_record_null_yn: str = "N"
    _filter_no_case_yn: str = "N"
    _filtered_method_name: str = field(init=False)

    @property
    def op_type(self):
        return self._operation_type

    @property
    def request_type(self):
        return self._request_type

    @property
    def identity_key(self):
        return self._identity_key

    @property
    def request_body(self):
        return self._request_body

    @property
    def filtered_yn(self):
        return self._filtered_yn

    @property
    def filtered_msg(self):
        return self._filtered_msg

    @property
    def filter_no_case_yn(self):
        return self._filter_no_case_yn

    @property
    def full_record_null_yn(self):
        return self._full_record_null_yn

    @property
    def filtered_method_name(self):
        return self._filtered_method_name

    @property
    def key_prd_no(self):
        return self._key_prd_no

    @property
    def key_prd_prc_no(self):
        return self._key_prd_prc_no

    @property
    def key_stock_no(self):
        return self._key_stock_no

    @property
    def key_coupon_no(self):
        return self._key_coupon_no

    @op_type.setter
    def op_type(self, value):
        self._operation_type = value

    @request_type.setter
    def request_type(self, value):
        self._request_type = value

    @identity_key.setter
    def identity_key(self, value):
        self._identity_key = value

    @request_body.setter
    def request_body(self, value):
        self._request_body = value

    @filtered_yn.setter
    def filtered_yn(self, value):
        self._filtered_yn = value

    @filtered_msg.setter
    def filtered_msg(self, value):
        self._filtered_msg = value

    @filter_no_case_yn.setter
    def filter_no_case_yn(self, value):
        self._filter_no_case_yn = value

    @full_record_null_yn.setter
    def full_record_null_yn(self, value):
        self._full_record_null_yn = value

    @filtered_method_name.setter
    def filtered_method_name(self, value):
        self._filtered_method_name = value

