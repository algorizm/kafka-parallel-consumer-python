# 아키텍처 상세 문서

## 📋 목차

1. [시스템 개요](#시스템-개요)
2. [핵심 컴포넌트](#핵심-컴포넌트)
3. [처리 흐름](#처리-흐름)
4. [설계 결정](#설계-결정)
5. [성능 최적화](#성능-최적화)

---

## 시스템 개요

### 목적
Kafka에서 메시지를 소비하고, 필터링을 거쳐 HTTP API로 요청을 전송하는 고성능 컨슈머 시스템입니다.

### 핵심 요구사항
1. **순서 보장**: 메시지 소비 순서에 따른 HTTP 요청 순서 보장
2. **고성능**: 높은 처리량 확보
3. **안정성**: 에러 처리, 재시도, 안전한 종료
4. **확장성**: 프로세스/스레드 수 조절 가능

---

## 핵심 컴포넌트

### 1. ConsumerMain (`base_process_consumer.py`)

**역할:**
- Kafka 메시지 소비
- 필터 적용 및 RequestURIMap 생성
- 큐 관리 및 워커 스레드 관리
- Offset 커밋 스케줄링

**주요 메서드:**
```python
class ConsumerMain:
    def consume(self, partition_no: int = None):
        """Kafka 메시지 소비 및 큐에 추가"""
        
    def start_concurrent_request(self, number: int = 1):
        """워커 스레드 시작"""
        
    def wait_done(self):
        """안전한 종료 처리"""
```

**핵심 로직:**
```python
# 메시지 소비
msg = self.consumer.poll(0.1)

# 필터 적용
filter_map = apply_filter(payload=self.payload, key=self.key)

# RequestURIMap 리스트 생성
_req_uri_map_list: list[RequestURIMap] = []
for _filter_result in filter_map:
    _req_map = make_request_map_with_offset(...)
    _req_uri_map_list.append(_req_map)

# 큐에 메시지 단위로 추가
self.request_queue.put(_req_uri_map_list)
```

### 2. SendHttpWorker (`base_process_worker.py`)

**역할:**
- 큐에서 메시지 가져오기
- HTTP 요청 순차 처리
- Offset 업데이트

**핵심 로직:**
```python
class SendHttpWorker(Thread):
    def run(self):
        while not self.event.is_set():
            record = self.queue.get(timeout=1)
            self.process_http_requests(record)
    
    def process_http_requests(self, request_items: List[RequestURIMap]):
        """HTTP 요청 순차 처리"""
        for item in request_items:
            if item.request_type is not RequestType.NO_BEHAVIOR:
                self.request_uri_no_session_map(req_map=item)
```

### 3. Filter System (`parallel_consumer/filter/`)

**역할:**
- 메시지 타입별 필터링 로직
- RequestURIMap 생성
- 비즈니스 로직 적용

**필터 예시:**
```python
def filter_live_prc_que_from_pd_prd(payload: dict) -> FilterResultMap:
    """상품 정보로부터 가격 큐 필터링"""
    # 필터링 로직
    # ...
    return FilterResultMap(...)
```

### 4. Request Handler (`parallel_consumer/utils/request.py`)

**역할:**
- HTTP 요청 처리
- 재시도 로직
- 에러 처리

**핵심 함수:**
```python
def request_uri_no_session_map(worker_name: str, req_map: RequestURIMap):
    """매 요청마다 새 세션으로 HTTP 요청"""
    with requests.session() as session:
        response = session.post(
            req_map.request_uri,
            headers=headers,
            json=req_map.request_body,
            timeout=HTTP_REQUEST_TIMEOUT,
        )
```

---

## 처리 흐름

### 1. 메시지 소비 단계

```
Kafka Broker
    ↓
ConsumerMain.consume()
    ↓
메시지 파싱 (parse_to_payload)
    ↓
필터 적용 (apply_filter)
    ↓
RequestURIMap 리스트 생성
    ↓
큐에 추가 (request_queue.put)
```

### 2. HTTP 요청 처리 단계

```
큐에서 메시지 가져오기 (queue.get)
    ↓
워커 스레드가 메시지 단위로 처리
    ↓
순차 처리 (for loop)
    ↓
HTTP 요청 (request_uri_no_session_map)
    ↓
Offset 업데이트 (update_offset_queue)
```

### 3. Offset 커밋 단계

```
Offset 큐에 추가 (offset_queue.put)
    ↓
스케줄러에 의해 주기적 커밋
    ↓
Kafka Broker에 커밋
```

---

## 설계 결정

### 1. 멀티프로세스 + 멀티스레드

**이유:**
- Python GIL 제약 회피
- 병렬 처리로 성능 최적화
- 프로세스 수 조절로 확장성 확보

**구현:**
```python
# 멀티프로세스
for i in range(NUMBER_OF_WORKERS):
    p = multiprocessing.Process(target=task, args=(process_event,))
    p.start()

# 멀티스레드
def start_concurrent_request(self, number: int = 1):
    for num in range(1, number + 1):
        req_thread = SendHttpWorker(...)
        req_thread.start()
```

### 2. 메시지 단위 큐 구조

**이유:**
- 메시지 내 HTTP 요청 순서 보장
- 원자성 보장
- Offset 관리 용이

**구현:**
```python
# 메시지 단위로 큐에 추가
_req_uri_map_list: list[RequestURIMap] = []
for _filter_result in filter_map:
    _req_map = make_request_map_with_offset(...)
    _req_uri_map_list.append(_req_map)

self.request_queue.put(_req_uri_map_list)
```

### 3. 동기 HTTP 요청

**이유:**
- HTTP 요청 순서 보장
- 에러 처리 및 재시도 로직 간단
- 운영 환경 안정성

**구현:**
```python
def process_http_requests(self, request_items: List[RequestURIMap]):
    for item in request_items:  # 순차 처리
        self.request_uri_no_session_map(req_map=item)  # 동기 HTTP
```

### 4. 매 요청마다 새 세션 생성

**이유:**
- L4 로드밸런서의 Session 기반 라운드 로빈
- 롤링 배포 시 안정성 확보
- 트래픽 분산 최적화

**구현:**
```python
def request_uri_no_session_map(self, req_map: RequestURIMap):
    with requests.session() as session:  # 매 요청마다 새 세션
        response = session.post(...)
```

---

## 성능 최적화

### 1. 멀티프로세스
- GIL 제약 회피
- CPU 코어 활용 극대화
- 프로세스 수 조절로 확장성 확보

### 2. 멀티스레드
- 여러 메시지 동시 처리
- 큐 기반 병렬 처리
- 스레드 수 조절로 처리량 조절

### 3. 큐 관리
- 큐 크기 제한으로 메모리 관리
- 타임아웃 설정으로 블로킹 방지
- 재시도 로직으로 안정성 확보

### 4. Offset 커밋 최적화
- 주기적 커밋으로 성능 최적화
- 메시지 단위 처리로 안전한 커밋
- 최대 offset 사용으로 중복 커밋 방지

---

## 안정성 확보

### 1. 에러 처리
- 예외 처리 및 로깅
- 에러 발생 시 알림 전송 (운영 환경)
- 안전한 종료 처리

### 2. 재시도 로직
- 네트워크 에러 시 재시도
- 재시도 횟수 제한
- 타임아웃 처리

### 3. 종료 처리
- SIGTERM/SIGINT 신호 처리
- 큐 비우기
- 스레드 안전 종료
- Offset 커밋

---

## 모니터링

### 1. 로깅
- 메시지 소비량
- 큐 크기
- HTTP 요청 처리량
- 에러 로그

### 2. 메트릭
- 초당 메시지 소비량
- 초당 HTTP 요청 처리량
- 큐 크기
- 스레드별 처리량

---

## 확장성

### 1. 프로세스 수 조절
```python
NUMBER_OF_WORKERS = 3  # 프로세스 수 조절
```

### 2. 스레드 수 조절
```python
CONCURRENT_REQUEST_THREAD_NUM = 15  # 스레드 수 조절
```

### 3. 큐 크기 조절
```python
QUEUE_MAX_SIZE = 90000  # 큐 크기 조절
```

---

## 참고 자료

- Kafka Consumer API: https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html
- Python Multiprocessing: https://docs.python.org/3/library/multiprocessing.html
- Python Threading: https://docs.python.org/3/library/threading.html

