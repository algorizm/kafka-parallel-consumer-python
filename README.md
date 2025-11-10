# Kafka Parallel Consumer (Python)

**한국어 / English**

Python 언어 특성에 맞게 구현한 고성능 Kafka 메시지 소비 및 HTTP 요청 처리 시스템. 독립적으로 개발한 후 Confluent Parallel Consumer와 구조적 유사성을 발견했습니다.

This is a high-performance Kafka message consumption and HTTP request processing system implemented in Python. After independent development, we discovered structural similarity with Confluent Parallel Consumer.

## 프로젝트 개요 / Project Overview

**한국어:**

이 프로젝트는 Kafka에서 메시지를 병렬로 소비하면서도 **메시지 소비 순서에 따른 HTTP 요청 순서 보장**을 보장하는 고성능 컨슈머 시스템입니다.

Python의 GIL(Global Interpreter Lock) 제약을 멀티프로세스로 회피하고, 멀티스레드를 조합하여 구현했습니다. 독립적으로 개발한 후, Confluent Parallel Consumer와 구조적 유사성을 발견했습니다.

**English:**

This project is a high-performance consumer system that processes Kafka messages in parallel while **guaranteeing HTTP request order based on message consumption order**.

We use multiprocessing to avoid Python GIL limits and combine it with multithreading. After independent development, we discovered structural similarity with Confluent Parallel Consumer.

### 주요 특징 / Key Features

**한국어:**

- **병렬 처리 아키텍처**: 멀티프로세스 + 비동기 큐 + 멀티스레드 구조 (Confluent Parallel Consumer와 유사)
- **순서 보장**: 동기 HTTP 요청으로 메시지 소비 순서에 따른 HTTP 요청 순서 보장
- **Python 최적화**: GIL 제약 회피를 위한 멀티프로세스 + 멀티스레드 조합
- **고성능**: 병렬 처리로 높은 처리량 달성
- **안정성**: 에러 처리, 재시도, 안전한 종료 처리
- **운영 고려**: L4 로드밸런서와 롤링 배포 환경을 고려한 설계

**English:**

- **Parallel Processing Architecture**: Multiprocessing + asynchronous queue + multithreading structure (similar to Confluent Parallel Consumer)
- **Ordering Guarantee**: Synchronous HTTP requests keep the order
- **Python Optimization**: Multiprocessing + multithreading to avoid GIL limits
- **High Performance**: Parallel processing for high throughput
- **Reliability**: Error handling, retry logic, and safe shutdown
- **Production-Ready**: Works with L4 load balancers and rolling deployments

## 아키텍처 / Architecture

### 시스템 구조 / System Structure

```
┌─────────────────────────────────────────────────────────┐
│              멀티프로세스 레벨 / Multiprocessing Level    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Process 1   │  │  Process 2   │  │  Process N   │ │
│  │              │  │              │  │              │ │
│  │  Consumer    │  │  Consumer    │  │  Consumer    │ │
│  │  ┌────────┐  │  │  ┌────────┐  │  │  ┌────────┐  │ │
│  │  │ Queue  │  │  │  │ Queue  │  │  │  │ Queue  │  │ │
│  │  │(Async) │  │  │  │(Async) │  │  │  │(Async) │  │ │
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

**아키텍처 특징 / Architecture Features:**

**한국어:**

- **멀티프로세스**: 각 프로세스가 독립적으로 Kafka 파티션을 소비
- **비동기 큐**: 프로세스 내부에 큐를 두어 메시지를 비동기적으로 전달
- **멀티스레드 워커**: 큐에서 메시지를 가져와 HTTP 요청을 병렬 처리

**English:**

- **Multiprocessing**: Each process consumes Kafka partitions independently
- **Asynchronous Queue**: Queue inside each process for asynchronous message delivery
- **Multithreaded Workers**: Get messages from queue and process HTTP requests in parallel

### 처리 흐름 / Processing Flow

**한국어:**

```
메시지 소비 (ConsumerMain.consume)
    ↓
필터 적용 (apply_filter)
    ↓
RequestURIMap 리스트 생성
    ↓
비동기 큐에 메시지 단위로 추가 (request_queue.put)
    ↓
워커 스레드가 큐에서 비동기적으로 가져오기 (queue.get)
    ↓
순차 처리 (process_http_requests - for loop)
    ↓
동기 HTTP 요청 (request_uri_no_session_map)
    ↓
Offset 업데이트 (update_offset_queue)
```

**English:**

```
Message Consumption (ConsumerMain.consume)
    ↓
Filter Application (apply_filter)
    ↓
RequestURIMap List Creation
    ↓
Add to Async Queue as Message Unit (request_queue.put)
    ↓
Worker Thread Retrieval (queue.get)
    ↓
Sequential Processing (process_http_requests - for loop)
    ↓
Synchronous HTTP Request (request_uri_no_session_map)
    ↓
Offset Update (update_offset_queue)
```

## 핵심 설계 결정 / Key Design Decisions

### 1. HTTP 순서 보장 / HTTP Ordering Guarantee

**구현 방식 / Implementation:**

**한국어:**

- 메시지 단위로 큐에 추가하여 원자성 보장
- 하나의 워커 스레드가 메시지 내 모든 HTTP 요청을 순차 처리
- 동기 HTTP(`requests` 라이브러리) 사용

**English:**

- Messages are added to queue as one unit
- One worker thread processes all HTTP requests in a message one by one
- Uses synchronous HTTP (with `requests` library)

```python
def process_http_requests(self, request_items: List[RequestURIMap]):
    for item in request_items:  # 순차 처리 / Sequential processing
        if item.request_type is not RequestType.NO_BEHAVIOR:
            self.request_uri_no_session_map(req_map=item)  # 동기 HTTP / Synchronous HTTP
```

### 2. 성능 최적화 전략 / Performance Optimization Strategy

**멀티프로세스 / Multiprocessing:**

**한국어:**

- GIL 제약 회피를 위해 멀티프로세스 사용
- 각 프로세스가 독립적으로 Kafka 파티션 소비

**English:**

- Uses multiprocessing to avoid GIL limits
- Each process consumes Kafka partitions independently

**멀티스레드 / Multithreading:**

**한국어:**

- 여러 워커 스레드로 메시지 병렬 처리
- 큐 기반으로 워커 스레드가 동시에 작업 수행

**English:**

- Multiple worker threads process messages in parallel
- Queue-based worker threads work at the same time

### 3. 세션 관리 전략 / Session Management Strategy

**매 요청마다 새 세션 생성 / New Session Per Request:**

**한국어:**

- L4 로드밸런서의 Session 기반 라운드 로빈을 고려
- 롤링 배포 시 안정성 확보
- 트래픽 분산 최적화

**English:**

- Works well with L4 load balancer session-based round-robin
- Keeps system stable during rolling deployments
- Better traffic distribution

```python
def request_uri_no_session_map(self, req_map: RequestURIMap):
    with requests.session() as session:  # 매 요청마다 새 세션 / New session per request
        response = session.post(...)
```

## 주요 컴포넌트 / Key Components

### 1. ConsumerMain (`base_process_consumer.py`)

**한국어:**

- Kafka 메시지 소비
- 필터 적용 및 RequestURIMap 생성
- 큐 관리 및 워커 스레드 관리
- Offset 커밋 스케줄링

**English:**

- Kafka message consumption
- Filter application and RequestURIMap generation
- Queue management and worker thread management
- Offset commit scheduling

### 2. SendHttpWorker (`base_process_worker.py`)

**한국어:**

- 큐에서 메시지 가져오기
- HTTP 요청 순차 처리
- Offset 업데이트

**English:**

- Gets messages from queue
- Processes HTTP requests one by one
- Updates offset

### 3. Filter System (`parallel_consumer/filter/`)

**한국어:**

- 메시지 타입별 필터링 로직
- RequestURIMap 생성

**English:**

- Filtering logic for each message type
- RequestURIMap generation

### 4. Request Handler (`parallel_consumer/utils/request.py`)

**한국어:**

- HTTP 요청 처리
- 재시도 로직
- 에러 처리

**English:**

- HTTP request processing
- Retry logic
- Error handling

## 기술 스택 / Tech Stack

- **Python**: 3.11+
- **Kafka Client**: confluent-kafka
- **HTTP Client**: requests, aiohttp
- **의존성 관리 / Dependency Management**: Poetry
- **로깅 / Logging**: Python logging (비동기 로깅 / async logging)

## 성능 특징 / Performance Characteristics

**한국어:**

- **병렬 처리 구조**: 멀티프로세스 + 비동기 큐 + 멀티스레드로 병렬 처리
- **순서 보장**: 메시지 단위 순차 처리로 HTTP 요청 순서 보장
- **안정성**: 에러 처리, 재시도, 안전한 종료 처리
- **확장성**: 프로세스 수 및 스레드 수 조절 가능

**English:**

- **Parallel Processing Structure**: Parallel processing with multiprocessing + async queue + multithreading
- **Ordering Guarantee**: Sequential processing per message keeps HTTP request order
- **Reliability**: Error handling, retry logic, and safe shutdown
- **Scalability**: Configurable process and thread counts

## 설정 / Configuration

### 환경 변수 / Environment Variables

```bash
# Kafka 설정 / Kafka Configuration
bootstrap.servers=localhost:9092
group.id=consumer-group
auto.offset.reset=earliest
enable.auto.commit=false

# API 서버 설정 / API Server Configuration
API_BASE_URL=http://localhost:8080
```

### 주요 설정 파라미터 / Key Configuration Parameters

```python
NUMBER_OF_WORKERS = 3  # 프로세스 수 / Number of processes
CONCURRENT_REQUEST_THREAD_NUM = 15  # 워커 스레드 수 / Number of worker threads
QUEUE_MAX_SIZE = 90000  # 큐 최대 크기 / Maximum queue size
HTTP_REQUEST_RETRY_LIMIT = 3  # 재시도 횟수 / Retry count
HTTP_REQUEST_TIMEOUT = 60  # 요청 타임아웃 (초) / Request timeout (seconds)
```

## 사용 예시 / Usage Example

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

## 학습 포인트 / Key Learnings

### 1. Confluent Parallel Consumer 패턴 구현 / Confluent Parallel Consumer Pattern Implementation

**한국어:**

- **병렬 처리 아키텍처 설계**
  - 멀티프로세스 + 큐 기반 워커 패턴
  - 병렬 메시지 처리와 순서 보장의 균형
  - 메시지 단위 처리로 원자성 보장
- **Python 언어 특성에 맞는 구현**
  - Python GIL 제약을 멀티프로세스로 회피
  - 멀티스레드로 I/O 바운드 작업 병렬 처리
  - 독립 개발 후 Confluent Parallel Consumer와 유사한 구조적 패턴 발견

**English:**

- **Parallel processing architecture design**
  - Multiprocessing + queue-based worker pattern
  - Balance between parallel processing and ordering guarantee
  - Message-level atomicity through unit processing
- **Python-specific implementation**
  - Use multiprocessing to avoid Python GIL limits
  - Use multithreading for parallel I/O-bound tasks
  - Discovered similar structural pattern to Confluent Parallel Consumer after independent development

### 2. 순서 보장과 성능의 균형 / Balancing Ordering and Performance

**한국어:**

- 비즈니스 요구사항(순서 보장)을 유지하면서 성능 최적화
- 멀티프로세스 + 멀티스레드로 병렬 처리

**English:**

- Optimize performance while keeping business requirements (ordering guarantee)
- Parallel processing with multiprocessing + multithreading

### 3. 운영 환경 고려 / Production Environment Considerations

**한국어:**

- L4 로드밸런서를 고려한 세션 관리
- 롤링 배포 안정성 확보

**English:**

- Session management for L4 load balancers
- Keep system stable during rolling deployments

### 4. 안정성 확보 / Reliability

**한국어:**

- 에러 처리 및 재시도 로직
- 안전한 종료 처리
- Offset 관리

**English:**

- Error handling and retry logic
- Safe shutdown handling
- Offset management

## 참고 자료 / References

- [Confluent Parallel Consumer](https://github.com/confluentinc/parallel-consumer) - 원본 Java 라이브러리 / Original Java library
- [아키텍처 상세 문서 / Architecture Documentation](./docs/ARCHITECTURE.md)
- [설계 결정 문서 / Design Decisions](./docs/DESIGN_DECISIONS.md)
- [코드 리뷰 결과 / Code Review Results](./PYTHON_CODE_REVIEW.md)

## Confluent Parallel Consumer와의 관계 / Relationship with Confluent Parallel Consumer

**한국어:**

이 프로젝트는 2023년 초에 팀 프로젝트 제약조건으로 Python으로 개발을 시작했습니다. 당시 비즈니스 요구사항(메시지 소비 순서에 따른 HTTP 요청 순서 보장)을 만족하기 위해 멀티프로세스 + 비동기 큐 + 멀티스레드 구조를 독립적으로 설계하여 구현했습니다.

2023년 말에 **Confluent Parallel Consumer**를 알게 되었고, 독립적으로 설계한 아키텍처가 검증된 라이브러리와 구조적으로 매우 유사함을 발견했습니다. 이는 설계 방향이 올바르게 선택되었음을 의미하며, Python 언어 특성에 맞춘 구현으로 차별화되었습니다.

**English:**

This project was developed in Python starting in early 2023, as Python was a requirement for the team project. To meet business requirements (guaranteeing HTTP request order based on message consumption order), we independently designed and implemented a multiprocessing + asynchronous queue + multithreading architecture.

In late 2023, we discovered **Confluent Parallel Consumer** and found that our independently designed architecture was structurally very similar to this proven library. This validates that our design direction was correct, and our implementation is differentiated by being optimized for Python language characteristics.

### 구조적 유사성 / Architectural Similarity

**한국어:**

**핵심 아키텍처 패턴:**
- 멀티프로세스로 파티션 레벨 병렬 처리
- 큐 기반 워커 스레드 패턴
- 메시지 단위 순서 보장
- 비동기 큐를 통한 메시지 처리

**English:**

**Core Architecture Pattern:**
- Multiprocessing for partition-level parallel processing
- Queue-based worker thread pattern
- Message-level ordering guarantee
- Message processing through asynchronous queue

### 공통점 / Common Features

**한국어:**

- 큐 기반 워커 스레드 패턴
- 메시지 단위 순서 보장
- 파티션 레벨 병렬 처리
- 높은 처리량을 위한 병렬 처리 구조

**English:**

- Queue-based worker thread pattern
- Message-level ordering guarantee
- Partition-level parallel processing
- Parallel processing structure for high throughput

### 차이점 / Differences

**한국어:**

**Confluent Parallel Consumer:**
- Java 기반 라이브러리로, Kafka의 `KafkaConsumer`를 래핑
- 내부 스레드 풀과 큐를 활용하여 단일 파티션 내에서도 다중 메시지를 병렬 처리
- `ParallelStreamProcessor`를 통해 메시지를 병렬로 처리하고, 사용자 콜백 함수로 처리 결과를 반환
- 처리된 메시지를 다른 Kafka 토픽으로 전달하거나 애플리케이션 로직으로 반환

**Python 프로젝트:**
- Kafka 메시지를 소비하여 프로세스 내부 비동기 큐에 추가
- 워커 스레드가 큐에서 메시지를 가져와 HTTP 요청으로 다른 서버에 전송
- Python 언어 특성에 맞춘 멀티프로세스 + 멀티스레드 구조

**English:**

**Confluent Parallel Consumer:**
- Java-based library that wraps Kafka's `KafkaConsumer`
- Uses internal thread pool and queue to process multiple messages in parallel within a single partition
- Processes messages in parallel through `ParallelStreamProcessor` and returns results via user callback functions
- Forwards processed messages to other Kafka topics or returns them to application logic

**The Python Project:**
- Consumes Kafka messages and adds them to an asynchronous queue within the process
- Worker threads retrieve messages from the queue and send HTTP requests to other servers
- Multiprocessing + multithreading structure optimized for Python language characteristics

### Python 특화 구현 / Python-Specific Implementation

**한국어:**

- **멀티프로세스**: Python GIL 제약 회피를 위한 필수 구조
- **멀티스레드**: 큐에서 메시지를 가져와 병렬 처리
- **동기 HTTP**: 비즈니스 요구사항(순서 보장)을 위한 선택

**English:**

- **Multiprocessing**: Required structure to avoid Python GIL limits
- **Multithreading**: Get messages from queue and process in parallel
- **Synchronous HTTP**: Choice for business requirements (ordering guarantee)

## 보안 고려사항 / Security Considerations

**한국어:**

이 포트폴리오 버전은 다음 정보를 제거/일반화했습니다:
- 내부 IP 주소 및 네트워크 정보
- 회사 특정 도메인 및 URL
- 실제 토픽 이름
- 인증 정보
- Slack 웹훅 URL

**English:**

This portfolio version has removed or generalized the following information:
- Internal IP addresses and network information
- Company-specific domains and URLs
- Actual topic names
- Authentication information
- Slack webhook URLs

## 라이선스 / License

**한국어:**

이 프로젝트는 MIT License로 라이선스되어 있습니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

이 프로젝트는 포트폴리오용으로 공개된 코드입니다. 실제 운영 환경에서 사용하려면 추가 보안 검토가 필요합니다.

**English:**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

This project is open-sourced for portfolio purposes. Additional security review is required for production use.

Copyright (c) 2023-2025 Hoyeop Lee
