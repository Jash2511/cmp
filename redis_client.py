import redis.asyncio as redis

REDIS_HOST = "localhost"
REDIS_PORT = 6379
QUEUE_NAME = "moderation_queue"

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)