# Kafka Parallel Consumer (Python)

A high-performance Kafka message consumption and HTTP request processing system implementing the core concepts of Confluent Parallel Consumer, optimized for Python language characteristics.

## Project Overview

This project implements the **core design principles of Confluent Parallel Consumer** in Python. 
It is a high-performance consumer system that processes Kafka messages in parallel while **guaranteeing HTTP request ordering based on message consumption order**.

By leveraging multiprocessing to overcome Python's GIL (Global Interpreter Lock) limitations and combining it with multithreading, we achieved performance comparable to the Java version.

### Key Features

- **Confluent Parallel Consumer Pattern**: Core concepts from the Java library implemented in Python
- **Ordering Guarantee**: Synchronous HTTP requests ensure HTTP request ordering matches message consumption order
- **Python Optimization**: Multiprocessing + multithreading combination to overcome GIL limitations
- **High Performance**: Parallel processing for high throughput
- **Reliability**: Error handling, retry logic, and graceful shutdown
- **Production-Ready**: Designed with L4 load balancers and rolling deployment in mind

## Architecture

### System Structure

```
┌─────────────────────────────────────────────────────────┐
│              Multiprocessing Level                       │
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

### Processing Flow

```
Message Consumption (ConsumerMain.consume)
    ↓
Filter Application (apply_filter)
    ↓
RequestURIMap List Creation
    ↓
Queue Message Unit Addition (request_queue.put)
    ↓
Worker Thread Retrieval (queue.get)
    ↓
Sequential Processing (process_http_requests - for loop)
    ↓
Synchronous HTTP Request (request_uri_no_session_map)
    ↓
Offset Update (update_offset_queue)
```

## Key Design Decisions

### 1. HTTP Ordering Guarantee

**Implementation:**
- Messages are added to the queue as atomic units
- A single worker thread processes all HTTP requests within a message sequentially
- Synchronous HTTP using the `requests` library

```python
def process_http_requests(self, request_items: List[RequestURIMap]):
    for item in request_items:  # Sequential processing
        if item.request_type is not RequestType.NO_BEHAVIOR:
            self.request_uri_no_session_map(req_map=item)  # Synchronous HTTP
```

### 2. Performance Optimization Strategy

**Multiprocessing:**
- Uses multiprocessing to overcome GIL limitations
- Each process independently consumes Kafka partitions

**Multithreading:**
- Multiple worker threads process messages in parallel
- Queue-based worker threads execute concurrently

### 3. Session Management Strategy

**New Session Per Request:**
- Considers L4 load balancer's session-based round-robin
- Ensures stability during rolling deployments
- Optimizes traffic distribution

```python
def request_uri_no_session_map(self, req_map: RequestURIMap):
    with requests.session() as session:  # New session per request
        response = session.post(...)
```

## Key Components

### 1. ConsumerMain (`base_process_consumer.py`)
- Kafka message consumption
- Filter application and RequestURIMap generation
- Queue management and worker thread management
- Offset commit scheduling

### 2. SendHttpWorker (`base_process_worker.py`)
- Message retrieval from queue
- Sequential HTTP request processing
- Offset updates

### 3. Filter System (`parallel_consumer/filter/`)
- Message type-specific filtering logic
- RequestURIMap generation

### 4. Request Handler (`parallel_consumer/utils/request.py`)
- HTTP request processing
- Retry logic
- Error handling

## Tech Stack

- **Python**: 3.11+
- **Kafka Client**: confluent-kafka
- **HTTP Client**: requests, aiohttp
- **Dependency Management**: Poetry
- **Logging**: Python logging (async logging)

## Performance Characteristics

- **Throughput**: High throughput with multiprocessing + multithreading
- **Ordering Guarantee**: Sequential processing per message ensures HTTP request ordering
- **Reliability**: Error handling, retry logic, and graceful shutdown
- **Scalability**: Configurable process and thread counts

## Configuration

### Environment Variables

```bash
# Kafka Configuration
bootstrap.servers=localhost:9092
group.id=consumer-group
auto.offset.reset=earliest
enable.auto.commit=false

# API Server Configuration
API_BASE_URL=http://localhost:8080
```

### Key Configuration Parameters

```python
NUMBER_OF_WORKERS = 3  # Number of processes
CONCURRENT_REQUEST_THREAD_NUM = 15  # Number of worker threads
QUEUE_MAX_SIZE = 90000  # Maximum queue size
HTTP_REQUEST_RETRY_LIMIT = 3  # Retry count
HTTP_REQUEST_TIMEOUT = 60  # Request timeout (seconds)
```

## Usage Example

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

## Key Learnings

### 1. Confluent Parallel Consumer Pattern Implementation
- **Implementing core Java library concepts in Python**
  - Balancing parallel message processing with ordering guarantees
  - Queue-based worker thread pattern
  - Message-level atomicity through unit processing
- **Language-specific optimization**
  - Overcoming Python GIL limitations with multiprocessing
  - Combining with multithreading for performance

### 2. Balancing Ordering and Performance
- Optimizing performance while maintaining business requirements (ordering guarantee)
- Parallel processing with multiprocessing + multithreading

### 3. Production Environment Considerations
- Session management for L4 load balancers
- Ensuring stability during rolling deployments

### 4. Reliability
- Error handling and retry logic
- Graceful shutdown handling
- Offset management

## References

- [Confluent Parallel Consumer](https://github.com/confluentinc/parallel-consumer) - Original Java library
- [Architecture Documentation](./docs/ARCHITECTURE.md)
- [Design Decisions](./docs/DESIGN_DECISIONS.md)
- [Code Review Results](./PYTHON_CODE_REVIEW.md)

## Relationship with Confluent Parallel Consumer

This project implements the **core design patterns of Confluent Parallel Consumer** in Python:

### Common Features
- High throughput through parallel message processing
- Message-level ordering guarantee
- Queue-based worker thread pattern
- Partition-level parallel processing

### Python-Specific Implementation
- **Multiprocessing**: Overcoming Python GIL limitations
- **Multithreading**: Parallel processing of I/O-bound tasks
- **Synchronous HTTP**: Explicit control for ordering guarantee

## Security Considerations

This portfolio version has removed/generalized the following information:
- Internal IP addresses and network information
- Company-specific domains and URLs
- Actual topic names
- Authentication information
- Slack webhook URLs

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2023-2025 Hoyeop Lee

This project is open-sourced for portfolio purposes. Additional security review is required for production use.

## Language Versions

- [English](README.md) (Current)
- [한국어](README.ko.md)

