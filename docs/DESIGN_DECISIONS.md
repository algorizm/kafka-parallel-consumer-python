# 설계 결정 문서

## 개요

이 문서는 Kafka Parallel Consumer Agent의 주요 설계 결정과 그 이유를 설명합니다.

---

## 1. HTTP 순서 보장 전략

### 결정
**메시지 단위 순차 처리 + 동기 HTTP 요청**

### 배경
비즈니스 요구사항으로 메시지 소비 순서에 따른 HTTP 요청 순서 보장이 필수적이었습니다.

### 선택지
1. **비동기 HTTP (asyncio)**: 순서 보장 어려움 
2. **동기 HTTP (requests)**: 순서 보장 가능 

### 구현
```python
def process_http_requests(self, request_items: List[RequestURIMap]):
 """메시지 내 HTTP 요청 순차 처리"""
 for item in request_items: # 순차 처리
 if item.request_type is not RequestType.NO_BEHAVIOR:
 self.request_uri_no_session_map(req_map=item) # 동기 HTTP
```

### 장점
- 메시지 내 HTTP 요청 순서 보장
- 에러 처리 및 재시도 로직 간단
- 운영 환경 안정성 확보

### 단점
- 비동기 HTTP 대비 성능 저하 가능
- 순차 처리로 인한 처리량 제한

### 트레이드오프
- **순서 보장 > 성능**: 비즈니스 요구사항 우선
- **안정성 > 성능**: 운영 환경 안정성 확보

---

## 2. 멀티프로세스 + 멀티스레드

### 결정
**멀티프로세스로 GIL 회피 + 멀티스레드로 병렬 처리**

### 배경
Python GIL 제약으로 인해 단일 프로세스 멀티스레드만으로는 성능 한계가 있었습니다.

### 선택지
1. **단일 프로세스 + 멀티스레드**: GIL 제약 
2. **멀티프로세스 + 단일 스레드**: 확장성 제한 
3. **멀티프로세스 + 멀티스레드**: 최적화 

### 구현
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

### 장점
- GIL 제약 회피
- CPU 코어 활용 극대화
- 프로세스/스레드 수 조절로 확장성 확보

### 단점
- 메모리 사용량 증가
- 프로세스 간 통신 복잡도 증가

### 트레이드오프
- **성능 > 메모리**: 높은 처리량 확보
- **확장성 > 복잡도**: 프로세스/스레드 수 조절 가능

---

## 3. 메시지 단위 큐 구조

### 결정
**메시지 단위로 큐에 추가하여 원자성 보장**

### 배경
메시지 내 여러 HTTP 요청을 하나의 단위로 처리하여 순서 보장과 원자성을 확보해야 했습니다.

### 선택지
1. **요청 단위 큐**: 순서 보장 어려움 
2. **메시지 단위 큐**: 원자성 보장 

### 구현
```python
# 메시지 단위로 큐에 추가
_req_uri_map_list: list[RequestURIMap] = []
for _filter_result in filter_map:
 _req_map = make_request_map_with_offset(...)
 _req_uri_map_list.append(_req_map)

self.request_queue.put(_req_uri_map_list) # 메시지 단위
```

### 장점
- 메시지 내 HTTP 요청 원자성 보장
- 순서 보장 용이
- Offset 관리 간단

### 단점
- 큐 크기 증가 가능
- 메모리 사용량 증가

### 트레이드오프
- **원자성 > 메모리**: 순서 보장과 안정성 확보

---

## 4. 세션 관리 전략

### 결정
**매 요청마다 새 세션 생성**

### 배경
L4 로드밸런서의 Session 기반 라운드 로빈과 롤링 배포 환경을 고려해야 했습니다.

### 선택지
1. **세션 재사용**: L4 로드밸런서 문제, 롤링 배포 시 에러 
2. **매 요청마다 새 세션**: 트래픽 분산, 안정성 확보 

### 구현
```python
def request_uri_no_session_map(self, req_map: RequestURIMap):
 """매 요청마다 새 세션으로 HTTP 요청"""
 with requests.session() as session: # 매 요청마다 새 세션
 response = session.post(...)
```

### 장점
- L4 로드밸런서 라운드 로빈 분배
- 롤링 배포 시 안정성 확보
- 트래픽 분산 최적화

### 단점
- 세션 생성 오버헤드
- 성능 저하 가능

### 트레이드오프
- **안정성 > 성능**: 운영 환경 안정성 우선
- **분산 > 성능**: 트래픽 분산 최적화

---

## 5. Offset 커밋 전략

### 결정
**주기적 커밋 + 메시지 처리 완료 후 커밋**

### 배경
성능과 안정성의 균형을 고려하여 Offset 커밋 전략을 결정해야 했습니다.

### 선택지
1. **즉시 커밋**: 성능 저하 
2. **주기적 커밋**: 균형 잡힌 전략 
3. **메시지 처리 완료 후 커밋**: 안전하지만 성능 저하 

### 구현
```python
# 주기적 커밋
def __schedule_commit(self, thread_id: int):
 while not self.offset_queue.empty():
 _partition, _offset = self.offset_queue.get()
 self.consumer.commit(
 offsets=[TopicPartition(topic=self.topic, partition=_partition, offset=_offset + 1)],
 asynchronous=True,
 )
```

### 장점
- 성능 최적화
- 안전한 커밋
- 중복 커밋 방지

### 단점
- 재시작 시 메시지 재처리 가능

### 트레이드오프
- **성능 > 재처리**: 주기적 커밋으로 성능 최적화

---

## 6. 에러 처리 전략

### 결정
**재시도 + 로깅 + Slack 알림**

### 배경
운영 환경에서 에러 발생 시 빠른 대응이 필요했습니다.

### 선택지
1. **에러 발생 시 즉시 종료**: 안정성 저하 
2. **재시도 + 로깅**: 균형 잡힌 전략 
3. **재시도 + 로깅 + 알림**: 최적 전략 

### 구현
```python
def retry_request_uri_no_session_map(
 self, worker_name: str, req_map: RequestURIMap, retry_cnt: int, errmsg
):
 if retry_cnt <= HTTP_REQUEST_RETRY_LIMIT:
 # 재시도 로직
 ...
 else:
 # 알림 전송 (예: Slack, 이메일 등)
 send_notification(text=msg)
```

### 장점
- 일시적 에러 복구
- 에러 추적 용이
- 빠른 대응 가능

### 단점
- 재시도로 인한 처리량 저하 가능

### 트레이드오프
- **안정성 > 성능**: 에러 복구와 추적 우선

---

## 7. 큐 관리 전략

### 결정
**큐 크기 제한 + 타임아웃 설정**

### 배경
메모리 관리와 블로킹 방지를 위해 큐 관리 전략이 필요했습니다.

### 선택지
1. **무제한 큐**: 메모리 위험 
2. **큐 크기 제한**: 균형 잡힌 전략 
3. **큐 크기 제한 + 타임아웃**: 최적 전략 

### 구현
```python
self.request_queue = queue.Queue(maxsize=queue_max_size)

# 타임아웃 설정
while not self.process_event.is_set():
 try:
 self.request_queue.put(_req_uri_map_list, timeout=1)
 break
 except queue.Full:
 time.sleep(0.1)
```

### 장점
- 메모리 관리
- 블로킹 방지
- 안정성 확보

### 단점
- 큐 가득 찰 시 메시지 소비 지연

### 트레이드오프
- **안정성 > 처리량**: 메모리 관리와 안정성 우선

---

## 요약

| 설계 결정 | 핵심 이유 | 트레이드오프 |
|----------|---------|------------|
| 동기 HTTP | 순서 보장 | 성능 < 순서 보장 |
| 멀티프로세스 + 멀티스레드 | GIL 회피 + 병렬 처리 | 메모리 < 성능 |
| 메시지 단위 큐 | 원자성 보장 | 메모리 < 안정성 |
| 매 요청마다 새 세션 | L4 로드밸런서 + 롤링 배포 | 성능 < 안정성 |
| 주기적 커밋 | 성능 최적화 | 재처리 < 성능 |
| 재시도 + 알림 | 에러 복구 + 추적 | 성능 < 안정성 |
| 큐 크기 제한 | 메모리 관리 | 처리량 < 안정성 |

---

## 결론

모든 설계 결정은 **비즈니스 요구사항(순서 보장)과 운영 환경 안정성을 우선**으로 하였습니다. 
성능보다는 안정성과 순서 보장을 우선시한 설계 결정들이었으며, 이는 실무에서 요구되는 중요한 고려사항입니다.

