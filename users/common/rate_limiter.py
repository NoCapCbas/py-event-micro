from fastapi import Request, HTTPException
from redis import Redis
from typing import Callable, Optional
import time
from .config import settings

class RateLimiter:
    def __init__(
        self,
        redis_client: Redis,
        requests: int = settings.RATE_LIMIT_REQUESTS,  # Number of requests allowed
        window: int = settings.RATE_LIMIT_WINDOW,    # Time window in seconds
        prefix: str = "rate_limit:"
    ):
        self.redis = redis_client
        self.requests = requests
        self.window = window
        self.prefix = prefix

    async def is_rate_limited(self, key: str) -> tuple[bool, Optional[int]]:
        current = time.time()
        window_start = current - self.window
        
        # Create a pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Remove old requests
        pipe.zremrangebyscore(key, 0, window_start)
        # Add current request
        pipe.zadd(key, {str(current): current})
        # Count requests in window
        pipe.zcount(key, window_start, current)
        # Set key expiration
        pipe.expire(key, self.window)
        
        # Execute pipeline
        _, _, request_count, _ = pipe.execute()
        
        # Check if rate limit exceeded
        is_limited = request_count > self.requests
        remaining = self.requests - request_count
        
        return is_limited, remaining

    def get_key(self, request: Request) -> str:
        # You can customize this to rate limit by different factors
        # e.g., IP + endpoint, or user ID if authenticated
        return f"{self.prefix}{request.client.host}"

class RateLimitMiddleware:
    def __init__(
        self,
        redis_client: Redis,
        requests_per_minute: int = 10
    ):
        self.limiter = RateLimiter(
            redis_client=redis_client,
            requests=requests_per_minute
        )

    async def __call__(
        self,
        request: Request,
        call_next: Callable
    ):
        # Skip rate limiting for certain paths (optional)
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)

        key = self.limiter.get_key(request)
        is_limited, remaining = await self.limiter.is_rate_limited(key)

        if is_limited:
            raise HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={
                    "Retry-After": str(self.limiter.window),
                    "X-RateLimit-Remaining": str(0)
                }
            )

        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.limiter.requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + self.limiter.window))
        
        return response
