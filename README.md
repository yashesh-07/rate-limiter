# Distributed Rate Limiter

A robust, high-performance rate-limiting service built using **FastAPI** and **Redis**. It limits incoming traffic based on IP addresses using a highly efficient **Lua script** evaluated directly on the Redis server in an atomic operation.

## High-Level Design (HLD)

### Architecture Overview

The system acts as a shield to your underlying application endpoints. It intercepts incoming HTTP requests globally, computes whether the client has surpassed their allowance, and either proxies the request or rejects it with an HTTP `429 Too Many Requests` status.

```mermaid
flowchart LR
    Client((Client)) -->|HTTP Request| Middleware[FastAPI Middleware]
    Middleware -->|Evaluate Request| Redis[(Redis Database)]
    Redis -.->|Return Status & Wait Time| Middleware
    Middleware -->|If OK - Next()| Endpoint[Target Endpoint]
    Middleware -->|If Limit Reached| ClientError((429 Response))
```

### Core Components

1. **FastAPI Server** (`app/main.py`):
   - Initializes the application and establishes a fast connection pool to Redis.
   - Includes a custom HTTP Middleware (`@app.middleware("http")`) that intercepts *every* incoming request before it reaches the router.
   - Extracts the client's IP address to act as a unique identifier key (`rate_limit:{IP}`).
   - **Fail-Open Strategy**: If the Redis server crashes or the connection times out, the middleware intentionally suppresses the exception and allows the traffic to pass through. This ensures that an infrastructure monitoring failure does not bring down your core application.

2. **Redis & Lua Scripting Engine** (`app/limiter.py`):
   - The core rate limit evaluation logic is completely offloaded to Redis via a Pre-registered Lua script (`lua_limiter`).
   - Using Lua guarantees that read-and-modify operations (fetching the current count, calculating times, incrementing) happen **atomically**. This prevents race conditions when a single user fires hundreds of parallel requests.
   - By returning precise wait-times directly from the script, it removes additional network ping-pongs between the App and the Cache.

3. **Docker Compose Setup** (`docker-compose.yml`):
   - **`app` container**: Based on `python:3.10-slim`. Installs FastAPI and maps the local `./app` folder as a volume for hot-reloading.
   - **`redis` container**: A lightweight `redis:alpine` instance acting as the fast in-memory datastore.

### Complete Execution Flow
1. **Interception**: A request hits the server. The middleware captures it and identifies the client IP.
2. **Evaluation**: Python invokes the pre-cached Redis Lua Script, passing the IP key, the current timestamp, `WINDOW_SIZE` (e.g. 60 seconds), and `MAX_REQ` (e.g. 10 requests).
3. **Atomic Processing (Inside Redis)**: 
   - *If the user is within limits:* Redis increments their counter and resets exactly when the key expires. It returns `[1, remaining_tokens]`.
   - *If the user exceeded limits:* Redis calculates exactly how many seconds are left in their penalty window without mutating the counter. It returns `[-1, wait_time_in_seconds]`.
4. **HTTP Response Generation**: 
   - **Blocked**: FastAPI short circuits the pipeline, returning a native `429 Too Many Requests` JSON response. It gracefully includes the `Retry-After: {wait_time}` header.
   - **Allowed**: FastAPI injects an `X-RateLimit-Remaining: {tokens}` header, and hands the request over to the main router to be fulfilled normally.

## Quick Start

### 1. Build and Run
Make sure you have Docker running, then execute:
```bash
docker-compose up -d --build
```

### 2. Testing
Send a simple GET Request:
```bash
curl -i http://localhost:8000/
```
You will notice the custom `X-RateLimit-Remaining` header in the response! 

Keep firing requests rapidly. Once you exceed the max requests (default `10` per `60` seconds), the server will block you with a `429` error and tell you exactly how many seconds are left until the window resets.