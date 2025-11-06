import os

# 환경 설정 (환경 변수에서 읽기, 기본값: DEV)
APP_ENVIRONMENT = os.getenv("APP_ENVIRONMENT", "DEV")


def base_uri():
    """API 서버 Base URL (환경 변수로 설정)"""
    if APP_ENVIRONMENT.upper() == "PROD":
        # 운영 환경: 환경 변수에서 읽기
        return os.getenv("API_BASE_URL_PROD", "http://localhost:8080")
    else:
        # 개발 환경: 환경 변수에서 읽기
        return os.getenv("API_BASE_URL_DEV", "http://localhost:8080")


def base_consumer_config(file_name: str):
    """컨슈머 설정 파일 경로"""
    if APP_ENVIRONMENT.upper() == "PROD":
        return f"parallel_consumer/configs/prod/.{file_name}"
    else:
        return f"parallel_consumer/configs/dev/.{file_name}"


# 재시도 설정
HTTP_REQUEST_RETRY_LIMIT = 3
HTTP_REQUEST_TIMEOUT = 60

# Offset 커밋 간격(초)
MESSAGE_COUNT_INTERVAL_SECONDS = 10
COMMIT_INTERVAL_SECONDS = 5
CHECK_END_INTERVAL_SECONDS = 10

# 커스텀 로그 레벨
MESSAGE_COUNT_LOG_LEVEL = 90
COMMIT_OFFSET_LOG_LEVEL = 91
REQUEST_TIME_LOG_LEVEL = 92
EACH_REQUEST_THREAD_LOG_LEVEL = 93
RETRY_REQUEST_LOG_LEVEL = 94

# 비동기 HTTP 클라이언트 설정
AIO_TCP_LIMIT_PER_HOST = 1
AIO_CLIENT_TIME_OUT = 60

