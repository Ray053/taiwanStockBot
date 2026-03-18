"""FastAPI application factory with startup events."""
import logging
import subprocess
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import scores, stocks, macro, admin, linebot

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_migrations():
    """Run alembic upgrade head on startup."""
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("Alembic migrations applied successfully.")
        else:
            logger.error(f"Alembic migration failed:\n{result.stderr}")
    except Exception as e:
        logger.error(f"Failed to run alembic migrations: {e}")


def cold_start_init():
    """On first deploy, seed stocks and run full FinMind pipeline if no kline data."""
    try:
        from app.database import SessionLocal
        from app.models.stock import Stock
        from app.models.kline import DailyKline
        db = SessionLocal()
        try:
            stock_count = db.query(Stock).count()
            kline_count = db.query(DailyKline).count()
        finally:
            db.close()

        # Step 1: sync stock list if empty
        if stock_count == 0:
            logger.info("Cold start: syncing stock list...")
            from app.scheduler.tasks import sync_stocks
            sync_stocks()

        # Step 2: run full pipeline if no kline data (first deploy)
        if kline_count == 0:
            logger.info("Cold start: no kline data, running full pipeline (institutional → signals → scoring)...")
            from app.scheduler.tasks import fetch_institutional, compute_signals, run_scoring
            fetch_institutional()
            compute_signals()
            run_scoring()
            logger.info("Cold start pipeline complete.")
        else:
            logger.info(f"Cold start: {stock_count} stocks, {kline_count} kline rows — skipping pipeline.")
    except Exception as e:
        logger.error(f"Cold start init error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Taiwan Stock Bot API...")
    run_migrations()

    # Run cold start in background so health check can respond immediately
    threading.Thread(target=cold_start_init, daemon=True, name="cold-start").start()

    from app.scheduler.scheduler import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler started within API process.")

    yield

    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped.")


app = FastAPI(
    title="Taiwan Stock AI Bot",
    description="全自動台股選股系統 — FinMind × Polymarket × FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(scores.router, prefix="/api/v1")
app.include_router(stocks.router, prefix="/api/v1")
app.include_router(macro.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(linebot.router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["health"])
def health_check():
    """Service health check."""
    return {"status": "ok", "service": "taiwan-stock-bot"}
