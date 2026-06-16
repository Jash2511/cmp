import asyncio
from redis_client import redis_client, QUEUE_NAME
from database import get_db_pool, get_platform_mapping, get_platform_by_id, get_platform_email_by_id, save_request_result
from aiAnalizer import GroqModerator
from email_client import send_email


async def moderation_worker():

    db_pool = await get_db_pool()


    platform_map = await get_platform_mapping(db_pool)
    print(f"Loaded Platform Map: {platform_map}")

    ai = GroqModerator()

    saved_bookmark = await redis_client.get("moderation_worker_bookmark")
    last_id = saved_bookmark if saved_bookmark else "0-0"
    print(f"Worker started. Resuming from Redis ID: {last_id}")

    try:
        while True:

            streams = await redis_client.xread({QUEUE_NAME: last_id}, count=1, block=5000)

            if not streams:
                continue

            stream_name, messages = streams[0]
            message_id, request_data = messages[0]


            request_id = request_data.get("request_id")
            text_to_check = request_data.get("text")
            age = request_data.get("age")

            print(f"\n--- Processing Job: {request_id} ---")


            platform_id = int(request_data.get("platform_id"))
            platform_name = platform_map.get(platform_id)


            if not platform_name:
                print(f"Platform ID '{platform_id}' not in local map. Fetching from DB...")
                platform_name = await get_platform_by_id(db_pool, platform_id)

                if platform_name:
                    print(f"Found platform '{platform_name}' in DB. Updating local map.")
                    platform_map[platform_id] = platform_name
                else:
                    print(f"⚠️ Warning: Unknown platform id '{platform_id}'. Skipping save.")
                    last_id = message_id
                    await redis_client.set("moderation_worker_bookmark", last_id)
                    continue

            ai_result = await asyncio.to_thread(
                ai.evaluate_text,
                text=text_to_check,
                platform=platform_name,
                age=age
            )

            post_category = ai_result.get("post_category")
            reasoning = ai_result.get("reasoning")
            confidence_score = ai_result.get("confidence_score")
            flagged_keywords = ai_result.get("flagged_keywords")
            await save_request_result(db_pool, request_id, platform_id, reasoning , post_category , confidence_score , flagged_keywords)

            if confidence_score < 0.7:
                platform_email = await get_platform_email_by_id(db_pool, platform_id)
                if platform_email:
                    subject = f"Low Confidence Moderation Alert for Request ID: {request_id}"
                    body = f"""
                    A moderation request for your platform, '{platform_name}', was processed with a low confidence score.

                    Request ID: {request_id}
                    Text: {text_to_check}
                    Category: {post_category}
                    Confidence: {confidence_score}
                    Reasoning: {reasoning}

                    Please review this case manually.
                    """
                    send_email(platform_email, subject, body)
                else:
                    print(f"⚠️ Could not find email for platform ID '{platform_id}'. Skipping email notification.")


            last_id = message_id
            await redis_client.set("moderation_worker_bookmark", last_id)

    except asyncio.CancelledError:
        print("Worker shutting down.")
    finally:

        await db_pool.close()
