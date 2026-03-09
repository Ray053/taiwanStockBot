"""LINE Messaging API + Telegram Bot notification service."""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 15


def _format_message(top_scores: list[dict]) -> str:
    lines = ["📊 台股每日選股報告\n"]
    for item in top_scores:
        rank = item.get("rank", "?")
        stock_id = item.get("stock_id", "")
        stock_name = item.get("stock_name", "")
        score = item.get("total_score", 0)
        reasons = item.get("breakdown", {}).get("reasons", [])
        reason_str = "\n  ".join(reasons[:3]) if reasons else "無"
        lines.append(f"#{rank} {stock_id} {stock_name} — {score:.1f} 分")
        lines.append(f"  {reason_str}\n")
    return "\n".join(lines)


def send_line_message(message: str) -> bool:
    """Send notification via LINE Messaging API (push message)."""
    token = settings.line_channel_access_token
    user_id = settings.line_user_id

    if not token or not user_id:
        logger.info("LINE Messaging API credentials not configured, skipping.")
        return False

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "to": user_id,
                    "messages": [{"type": "text", "text": message}],
                },
            )
            resp.raise_for_status()
            logger.info("LINE message sent successfully")
            return True
    except Exception as e:
        logger.error(f"LINE Messaging API error: {e}")
        return False


def send_telegram(message: str) -> bool:
    """Send notification via Telegram Bot."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or token == "your_telegram_bot_token":
        logger.info("Telegram token not configured, skipping.")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"})
            resp.raise_for_status()
            logger.info("Telegram notification sent successfully")
            return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def send_top_scores_notification(top_scores: list[dict]) -> None:
    """Format and send top scores via all configured channels."""
    if not top_scores:
        logger.info("No scores to notify.")
        return

    message = _format_message(top_scores)
    send_line_message(message)
    send_telegram(message)
