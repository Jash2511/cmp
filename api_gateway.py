import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from redis_client import redis_client, QUEUE_NAME
from database import get_db_pool, register_platform

app = FastAPI(
    title="AI Content Moderation API Gateway",
    description="Receives moderation requests and pushes them to Redis queue",
    version="1.0"
)

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================
# Request Schemas
# ==========================

class ModerationRequest(BaseModel):
    text: str = Field(..., min_length=1)
    platform_id: int
    age: str

class PlatformRegistrationRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr # Pydantic will validate the email format


# ==========================
# Health Check
# ==========================

@app.get("/")
async def health_check():
    health_status = {
        "status": "running",
        "service": "content-moderation-api-gateway",
        "dependencies": {
            "redis": "unknown",
            "database": "unknown"
        }
    }
    
    # Check Redis
    try:
        await redis_client.ping()
        health_status["dependencies"]["redis"] = "ok"
    except Exception as e:
        health_status["dependencies"]["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # Check Database
    db_pool = None
    try:
        db_pool = await get_db_pool()
        async with db_pool.acquire() as conn:
            await conn.execute("SELECT 1")
        health_status["dependencies"]["database"] = "ok"
    except Exception as e:
        health_status["dependencies"]["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    finally:
        if db_pool:
            await db_pool.close()

    return health_status


# ==========================
# Platform Registration
# ==========================

@app.post("/register-platform")
async def register_platform_endpoint(request: PlatformRegistrationRequest):
    db_pool = None
    try:
        db_pool = await get_db_pool()
        new_id = await register_platform(db_pool, request.name, request.email)
        
        if new_id:
            return {
                "status": "success",
                "message": f"Platform '{request.name}' registered successfully.",
                "platform_id": new_id
            }
        else:
            # This happens if the platform name already exists
            raise HTTPException(
                status_code=409, # 409 Conflict
                detail=f"Platform '{request.name}' already exists."
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions so FastAPI can handle them correctly
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register platform: {str(e)}"
        )
    finally:
        if db_pool:
            await db_pool.close()


# ==========================
# Queue Moderation Request
# ==========================

@app.post("/moderate")
async def moderate_content(request: ModerationRequest):

    try:

        request_id = str(uuid.uuid4())

        event = {
            "request_id": request_id,
            "text": request.text,
            "platform_id": request.platform_id,
            "age": request.age,
            "timestamp": datetime.utcnow().isoformat()
        }

        await redis_client.xadd(QUEUE_NAME,event)

        queue_size = await redis_client.xlen(QUEUE_NAME)

        return {
            "status": "queued",
            "request_id": request_id,
            "queue_name": QUEUE_NAME,
            "queue_size": queue_size
        }

    except HTTPException:
        raise
    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue request: {str(e)}"
        )


# ==========================
# Queue Statistics
# ==========================

@app.get("/queue/stats")
async def queue_stats():

    try:

        return {
            "queue_name": QUEUE_NAME,
            "queue_size": await redis_client.xlen(QUEUE_NAME)
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ==========================
# List Platforms
# ==========================

@app.get("/platforms")
async def list_platforms():
    db_pool = None
    try:
        db_pool = await get_db_pool()
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, name, email FROM platforms ORDER BY id")
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db_pool:
            await db_pool.close()


# ==========================
# Moderation Results
# ==========================

@app.get("/moderation-results")
async def get_moderation_results(platform_id: int = Query(None)):
    db_pool = None
    try:
        db_pool = await get_db_pool()
        async with db_pool.acquire() as conn:
            if platform_id:
                rows = await conn.fetch(
                    """SELECT mr.request_id, mr.platform_id, p.name as platform_name,
                              mr.reason, mr.post_category, mr.confidence_score,
                              mr.flagged_keywords, mr.completed_at
                       FROM moderation_results mr
                       JOIN platforms p ON mr.platform_id = p.id
                       WHERE mr.platform_id = $1
                       ORDER BY mr.completed_at DESC""",
                    platform_id
                )
            else:
                rows = await conn.fetch(
                    """SELECT mr.request_id, mr.platform_id, p.name as platform_name,
                              mr.reason, mr.post_category, mr.confidence_score,
                              mr.flagged_keywords, mr.completed_at
                       FROM moderation_results mr
                       JOIN platforms p ON mr.platform_id = p.id
                       ORDER BY mr.completed_at DESC"""
                )
            results = []
            for row in rows:
                r = dict(row)
                r["request_id"] = str(r["request_id"])
                if r["completed_at"]:
                    r["completed_at"] = r["completed_at"].isoformat()
                results.append(r)
            return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db_pool:
            await db_pool.close()


# ==========================
# Admin Dashboard Stats
# ==========================

@app.get("/admin/dashboard-stats")
async def admin_dashboard_stats():
    db_pool = None
    try:
        db_pool = await get_db_pool()
        async with db_pool.acquire() as conn:
            total_platforms = await conn.fetchval("SELECT COUNT(*) FROM platforms")
            total_results = await conn.fetchval("SELECT COUNT(*) FROM moderation_results")
            avg_confidence = await conn.fetchval("SELECT AVG(confidence_score) FROM moderation_results")
            category_rows = await conn.fetch(
                """SELECT post_category, COUNT(*) as count
                   FROM moderation_results
                   GROUP BY post_category
                   ORDER BY count DESC"""
            )
            categories = {row["post_category"]: row["count"] for row in category_rows}

            queue_size = 0
            try:
                queue_size = await redis_client.xlen(QUEUE_NAME)
            except Exception:
                pass

            return {
                "total_platforms": total_platforms,
                "total_moderation_results": total_results,
                "avg_confidence_score": round(float(avg_confidence), 3) if avg_confidence else 0,
                "categories": categories,
                "queue_size": queue_size
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db_pool:
            await db_pool.close()