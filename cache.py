from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

from config import settings


async def init_cache():
    try:
        # Подключаемся к Redis
        redis = aioredis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)
        FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    except Exception:
        # Fallback на in-memory кэш если Redis недоступен
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
