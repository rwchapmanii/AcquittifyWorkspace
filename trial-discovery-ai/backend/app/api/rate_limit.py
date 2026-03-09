from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic, time

from fastapi import Request
from redis import Redis
from redis.exceptions import RedisError


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> RateLimitDecision:
        now = monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_attempts:
                oldest = bucket[0] if bucket else now
                retry_after = max(1, int(self.window_seconds - (now - oldest)))
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)

            bucket.append(now)
            return RateLimitDecision(allowed=True)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


class RedisRateLimiter:
    def __init__(
        self,
        *,
        redis_url: str,
        max_attempts: int,
        window_seconds: int,
        key_prefix: str = "auth_rate_limit",
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._key_prefix = key_prefix
        self._redis = Redis.from_url(redis_url, decode_responses=True)

    def _bucket_key(self, key: str) -> str:
        bucket = int(time() // self.window_seconds)
        return f"{self._key_prefix}:{bucket}:{key}"

    def allow(self, key: str) -> RateLimitDecision:
        bucket_key = self._bucket_key(key)
        try:
            current = self._redis.incr(bucket_key)
            if current == 1:
                self._redis.expire(bucket_key, self.window_seconds + 1)
            if current > self.max_attempts:
                ttl = self._redis.ttl(bucket_key)
                retry_after = ttl if isinstance(ttl, int) and ttl > 0 else 1
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
            return RateLimitDecision(allowed=True)
        except RedisError:
            # Fail open so auth does not go down if Redis is temporarily unavailable.
            return RateLimitDecision(allowed=True)

    def reset(self) -> None:
        # Not used in runtime; tests currently run with in-memory limiter.
        return None


def get_request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        candidate = forwarded_for.split(",", 1)[0].strip()
        if candidate:
            return candidate

    if request.client and request.client.host:
        return request.client.host
    return "unknown"
