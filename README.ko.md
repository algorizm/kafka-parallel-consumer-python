# Kafka Parallel Consumer (Python)

Confluent Parallel Consumer의 핵심 개념을 Python 언어 특성에 맞게 구현한 고성능 Kafka 메시지 소비 및 HTTP 요청 처리 시스템

##  프로젝트 개요

이 프로젝트는 **Confluent Parallel Consumer**의 핵심 설계 원리를 Python 언어로 구현한 것입니다. 
Kafka에서 메시지를 병렬로 소비하면서도 **메시지 소비 순서에 따른 HTTP 요청 순서 보장**을 보장하는 고성능 컨슈머 시스템입니다.

Python의 GIL(Global Interpreter Lock) 제약을 멀티프로세스로 회피하고, 멀티스레드를 조합하여 Java 버전과 유사한 성능을 달성했습니다.

### 주요 특징

-  **Confluent Parallel Consumer 패턴**: Java 라이브러리의 핵심 개념을 Python으로 구현
-  **순서 보장**: 동기 HTTP 요청으로 메시지 소비 순서에 따른 HTTP 요청 순서 보장
-  **Python 최적화**: GIL 제약 회피를 위한 멀티프로세스 + 멀티스레드 조합
-  **고성능**: 병렬 처리로 높은 처리량 달성
-  **안정성**: 에러 처리, 재시도, 안전한 종료 처리
-  **운영 고려**: L4 로드밸런서와 롤링 배포 환경을 고려한 설계

##  아키텍처

### 시스템 구조

```
┌─────────────────────────────────────────────────────────┐
│                  멀티프로세스 레벨                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Process 1   │  │  Process 2   │  │  Process N   │ │
│  │              │  │              │  │              │ │
│  │  Consumer    │  │  Consumer    │  │  Consumer    │ │
│  │  ┌────────┐  │  │  ┌────────┐  │  │  ┌────────┐  │ │
│  │  │ Queue  │  │  │  │ Queue  │  │  │  │ Queue  │  │ │
│  │  └───┬────┘  │  │  └───┬────┘  │  │  └───┬────┘  │ │
│  │      │       │  │      │       │  │      │       │ │
│  │  ┌───▼───┐   │  │  ┌───▼───┐   │  │  ┌───▼───┐   │ │
│  │  │Thread1│   │  │  │Thread1│   │  │  │Thread1│   │ │
│  │  │Thread2│   │  │  │Thread2│   │  │  │Thread2│   │ │
│  │  │ThreadN│   │  │  │ThreadN│   │  │  │ThreadN│   │ │
│  │  └───────┘   │  │  └───────┘   │  │  └───────┘   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 처리 흐름

```
메시지 소비 (ConsumerMain.consume)
    ↓
필터 적용 (apply_filter)
    ↓
RequestURIMap 리스트 생성
    ↓
큐에 메시지 단위로 추가 (request_queue.put)
    ↓
워커 스레드가 큐에서 가져오기 (queue.get)
    ↓
순차 처리 (process_http_requests - for loop)
    ↓
동기 HTTP 요청 (request_uri_no_session_map)
    ↓
Offset 업데이트 (update_offset_queue)
```

##  핵심 설계 결정

### 1. HTTP 순서 보장

**구현 방식:**
- 메시지 단위로 큐에 추가하여 원자성 보장
- 하나의 워커 스레드가 메시지 내 모든 HTTP 요청을 순차 처리
- 동기 HTTP(`requests` 라이브러리) 사용

```python
def process_http_requests(self, request_items: List[RequestURIMap]):
    for item in request_items:  # 순차 처리
        if item.request_type is not RequestType.NO_BEHAVIOR:
            self.request_uri_no_session_map(req_map=item)  # 동기 HTTP
```

### 2. 성능 최적화 전략

**멀티프로세스:**
- GIL 제약 회피를 위해 멀티프로세스 사용
- 각 프로세스가 독립적으로 Kafka 파티션 소비

**멀티스레드:**
- 여러 워커 스레드로 메시지 병렬 처리
- 큐 기반으로 워커 스레드가 동시에 작업 수행

### 3. 세션 관리 전략

**매 요청마다 새 세션 생성:**
- L4 로드밸런서의 Session 기반 라운드 로빈을 고려
- 롤링 배포 시 안정성 확보
- 트래픽 분산 최적화

```python
def request_uri_no_session_map(self, req_map: RequestURIMap):
    with requests.session() as session:  # 매 요청마다 새 세션
        response = session.post(...)
```

##  주요 컴포넌트

### 1. ConsumerMain (`base_process_consumer.py`)
- Kafka 메시지 소비
- 필터 적용 및 RequestURIMap 생성
- 큐 관리 및 워커 스레드 관리
- Offset 커밋 스케줄링

### 2. SendHttpWorker (`base_process_worker.py`)
- 큐에서 메시지 가져오기
- HTTP 요청 순차 처리
- Offset 업데이트

### 3. Filter System (`parallel_consumer/filter/`)
- 메시지 타입별 필터링 로직
- RequestURIMap 생성

### 4. Request Handler (`parallel_consumer/utils/request.py`)
- HTTP 요청 처리
- 재시도 로직
- 에러 처리

##  기술 스택

- **Python**: 3.11+
- **Kafka Client**: confluent-kafka
- **HTTP Client**: requests, aiohttp
- **의존성 관리**: Poetry
- **로깅**: Python logging (비동기 로깅)

##  성능 특징

- **처리량**: 멀티프로세스 + 멀티스레드로 높은 처리량
- **순서 보장**: 메시지 단위 순차 처리로 HTTP 요청 순서 보장
- **안정성**: 에러 처리, 재시도, 안전한 종료 처리
- **확장성**: 프로세스 수 및 스레드 수 조절 가능

##  설정

### 환경 변수

```bash
# Kafka 설정
bootstrap.servers=localhost:9092
group.id=consumer-group
auto.offset.reset=earliest
enable.auto.commit=false

# API 서버 설정
API_BASE_URL=http://localhost:8080
```

### 주요 설정 파라미터

```python
NUMBER_OF_WORKERS = 3  # 프로세스 수
CONCURRENT_REQUEST_THREAD_NUM = 15  # 워커 스레드 수
QUEUE_MAX_SIZE = 90000  # 큐 최대 크기
HTTP_REQUEST_RETRY_LIMIT = 3  # 재시도 횟수
HTTP_REQUEST_TIMEOUT = 60  # 요청 타임아웃 (초)
```

##  사용 예시

```python
from parallel_consumer.base.base_process_consumer import ConsumerMain
from parallel_consumer.base.concurrent_logger import BatchQueueLog

logger = BatchQueueLog(log_dir="logs", log_name="consumer")
config = {
    "bootstrap.servers": "localhost:9092",
    "group.id": "consumer-group",
    "auto.offset.reset": "earliest",
}

consumer = ConsumerMain(
    config=config,
    topic_name="example-topic",
    logger_cls=logger,
    event=multiprocessing.Event(),
    queue_max_size=90000,
)

consumer.start_concurrent_request(number=15)
consumer.consume()
```

##  학습 포인트

### 1. Confluent Parallel Consumer 패턴 구현
- **Java 라이브러리의 핵심 개념을 Python으로 구현**
  - 병렬 메시지 처리와 순서 보장의 균형
  - 큐 기반 워커 스레드 패턴
  - 메시지 단위 처리로 원자성 보장
- **언어 특성에 맞는 최적화**
  - Python GIL 제약을 멀티프로세스로 회피
  - 멀티스레드와의 조합으로 성능 확보

### 2. 순서 보장과 성능의 균형
- 비즈니스 요구사항(순서 보장)을 유지하면서 성능 최적화
- 멀티프로세스 + 멀티스레드로 병렬 처리

### 3. 운영 환경 고려
- L4 로드밸런서를 고려한 세션 관리
- 롤링 배포 안정성 확보

### 4. 안정성 확보
- 에러 처리 및 재시도 로직
- 안전한 종료 처리
- Offset 관리

##  참고 자료

- [Confluent Parallel Consumer](https://github.com/confluentinc/parallel-consumer) - 원본 Java 라이브러리
- [아키텍처 상세 문서](./docs/ARCHITECTURE.md)
- [설계 결정 문서](./docs/DESIGN_DECISIONS.md)
- [코드 리뷰 결과](./PYTHON_CODE_REVIEW.md)

##  Confluent Parallel Consumer와의 관계

이 프로젝트는 **Confluent Parallel Consumer**의 핵심 설계 패턴을 Python 언어로 구현한 것입니다:

### 공통점
-  병렬 메시지 처리로 높은 처리량 달성
-  메시지 단위 순서 보장
-  큐 기반 워커 스레드 패턴
-  파티션 레벨 병렬 처리

### Python 특화 구현
-  **멀티프로세스**: Python GIL 제약 회피
-  **멀티스레드**: I/O 바운드 작업 병렬 처리
-  **동기 HTTP**: 순서 보장을 위한 명시적 제어

##  보안 고려사항

이 포트폴리오 버전은 다음 정보를 제거/일반화했습니다:
- 내부 IP 주소 및 네트워크 정보
- 회사 특정 도메인 및 URL
- 실제 토픽 이름
- 인증 정보
- Slack 웹훅 URL

##  라이선스

이 프로젝트는 MIT License로 라이선스되어 있습니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

Copyright (c) 2023-2025 Hoyeop Lee

이 프로젝트는 포트폴리오용으로 공개된 코드입니다. 실제 운영 환경에서 사용하려면 추가 보안 검토가 필요합니다.

##  언어 버전

- [English](README.md)
- [한국어](README.ko.md) (현재)

