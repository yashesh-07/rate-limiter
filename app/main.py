import os
import time
import redis
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from limiter import LUA_SLIDING_WINDOW

app = FastAPI()

# Load constants
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
MAX_REQ = int(os.getenv("RATE_LIMIT_MAX", 10))
WINDOW = int(os.getenv("WINDOW_SIZE", 60))

try:
    # Use the service name 'redis' defined in docker-compose
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=0.1)
    # Pre-register the script for Low Latency
    lua_limiter = r.register_script(LUA_SLIDING_WINDOW)
    logging.info("Redis and Lua script loaded successfully.")
except Exception as e:
    logging.error(f"Redis initialization failed: {e}")
    r = None

@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    if r:
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_key = f"rate_limit:{client_ip}"
            now = time.time()
            
            # The script now returns a list: [status, value]
            status, value = lua_limiter(keys=[user_key], args=[now, WINDOW, MAX_REQ])

            if status == -1:
                # Inform the user via a custom header and a clear message
                wait_seconds = int(value)
                return JSONResponse(
                    status_code=429, 
                    content={"detail": f"Rate limit exceeded. Try again in {wait_seconds} seconds."},
                    headers={"Retry-After": str(wait_seconds)}
                )
            
            # Optional: Add remaining limit to successful response headers
            response = await call_next(request)
            response.headers["X-RateLimit-Remaining"] = str(int(value))
            return response
                
        except redis.RedisError:
            pass 
            
    return await call_next(request)

@app.get("/")
async def home():
    return {"status": "success", "info": "Rate limiter is active"}