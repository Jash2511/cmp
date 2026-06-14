import json
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from redis_client import redis_client, QUEUE_NAME

app = FastAPI(
    title="AI Content Moderation API Gateway",
    description="Receives moderation requests and pushes them to Redis queue",
    version="1.0"
)


# ==========================
# Request Schema
# ==========================

class ModerationRequest(BaseModel):
    text: str = Field(..., min_length=1)
    platform: str
    age: str


# ==========================
# Health Check
# ==========================

@app.get("/")
def health_check():
    return {
        "status": "running",
        "service": "content-moderation-api-gateway"
    }


# ==========================
# Queue Moderation Request
# ==========================

@app.post("/moderate")
def moderate_content(request: ModerationRequest):

    try:

        request_id = str(uuid.uuid4())

        event = {
            "request_id": request_id,
            "text": request.text,
            "platform": request.platform,
            "age": request.age,
            "timestamp": datetime.utcnow().isoformat()
        }

        redis_client.lpush(
            QUEUE_NAME,
            json.dumps(event)
        )

        queue_size = redis_client.llen(QUEUE_NAME)

        return {
            "status": "queued",
            "request_id": request_id,
            "queue_name": QUEUE_NAME,
            "queue_size": queue_size
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue request: {str(e)}"
        )


# ==========================
# Queue Statistics
# ==========================

@app.get("/queue/stats")
def queue_stats():

    try:

        return {
            "queue_name": QUEUE_NAME,
            "queue_size": redis_client.llen(QUEUE_NAME)
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )