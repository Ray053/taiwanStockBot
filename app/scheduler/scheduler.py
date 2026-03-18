"""APScheduler initialization with Asia/Taipei timezone."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.scheduler.tasks import (
    sync_stocks,
    fetch_polymarket,
    fetch_institutional,
    compute_signals,
    run_scoring,
    send_notification,
    fetch_us_afterhours,
)

logger = logging.getLogger(__name__)

TIMEZONE = "Asia/Taipei"


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TIMEZONE)

    # 每週日 02:00 — Sync all TWSE stocks from FinMind
    scheduler.add_job(
        sync_stocks,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone=TIMEZONE),
        id="sync_stocks",
        name="Sync all TWSE stocks from FinMind",
        replace_existing=True,
    )

    # 06:00 — Fetch Polymarket macro snapshot
    scheduler.add_job(
        fetch_polymarket,
        trigger=CronTrigger(hour=6, minute=0, timezone=TIMEZONE),
        id="fetch_polymarket",
        name="Fetch Polymarket macro snapshot",
        replace_existing=True,
    )

    # 08:30 → 改到收盤後 14:10，FinMind 三大法人當日資料收盤後才可用
    scheduler.add_job(
        fetch_institutional,
        trigger=CronTrigger(hour=14, minute=10, timezone=TIMEZONE),
        id="fetch_institutional",
        name="Fetch institutional investors (三大法人)",
        replace_existing=True,
    )

    # 09:05 → 改到收盤後 14:20，K線需等收盤才完整
    scheduler.add_job(
        compute_signals,
        trigger=CronTrigger(hour=14, minute=20, timezone=TIMEZONE),
        id="compute_signals",
        name="Compute technical signals",
        replace_existing=True,
    )

    # 14:05 → 14:35，等上兩個任務完成後再評分
    scheduler.add_job(
        run_scoring,
        trigger=CronTrigger(hour=14, minute=35, timezone=TIMEZONE),
        id="run_scoring",
        name="Run multi-factor scoring",
        replace_existing=True,
    )

    # 14:30 → 14:50
    scheduler.add_job(
        send_notification,
        trigger=CronTrigger(hour=14, minute=50, timezone=TIMEZONE),
        id="send_notification",
        name="Send LINE/Telegram notification",
        replace_existing=True,
    )

    # 23:00 — US afterhours data
    scheduler.add_job(
        fetch_us_afterhours,
        trigger=CronTrigger(hour=23, minute=0, timezone=TIMEZONE),
        id="fetch_us_afterhours",
        name="Fetch US afterhours data",
        replace_existing=True,
    )

    logger.info(f"Scheduler created with {len(scheduler.get_jobs())} jobs (timezone={TIMEZONE})")
    return scheduler
