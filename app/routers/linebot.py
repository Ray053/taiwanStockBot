"""LINE Bot Webhook endpoint with signature verification."""
import hashlib
import hmac
import base64
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.services.line_handler import handle_text_message, handle_postback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linebot", tags=["linebot"])


def _verify_signature(body: bytes, x_line_signature: str) -> bool:
    """Verify LINE webhook signature (HMAC-SHA256)."""
    secret = settings.line_channel_secret
    if not secret:
        logger.warning("LINE channel secret not configured — skipping signature check")
        return True
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, x_line_signature)


@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str = Header(default=""),
):
    body = await request.body()

    if not _verify_signature(body, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    events = payload.get("events", [])

    for event in events:
        event_type = event.get("type")
        reply_token = event.get("replyToken", "")

        if event_type == "message":
            msg = event.get("message", {})
            if msg.get("type") == "text":
                handle_text_message(reply_token, msg.get("text", ""))

        elif event_type == "postback":
            data = event.get("postback", {}).get("data", "")
            handle_postback(reply_token, data)

        elif event_type == "follow":
            # New follower — send welcome message
            handle_text_message(reply_token, "說明")

    return {"status": "ok"}
