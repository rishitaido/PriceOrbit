"""Scheduled and manual price update jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product_model import Product
from app.services.product_service import ProductService

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


LOGGER_NAME = "priceorbit.price_updates"
LOG_DIR = Path("app/logs")
LOG_FILE = LOG_DIR / "price_updates.log"
LOCK_FILE = LOG_DIR / "price_updater.lock"


def _configure_job_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = True

    has_file_handler = any(
        isinstance(handler, logging.FileHandler) and handler.baseFilename == str(LOG_FILE.resolve())
        for handler in logger.handlers
    )
    if not has_file_handler:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        logger.addHandler(file_handler)

    return logger


job_logger = _configure_job_logger()


class PriceUpdateScheduler:
    """Owns scheduler lifecycle and manual trigger execution."""

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._run_lock = asyncio.Lock()
        self._current_task: Optional[asyncio.Task[Dict[str, Any]]] = None
        self._lock_handle: Optional[TextIO] = None
        self._started = False
        self._state: Dict[str, Any] = {
            "scheduler_enabled": False,
            "running": False,
            "last_run_started_at": None,
            "last_run_finished_at": None,
            "last_run_result": None,
            "last_run_source": None,
        }

    def _acquire_file_lock(self) -> bool:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._lock_handle = LOCK_FILE.open("a+", encoding="utf-8")
        if fcntl is None:  # pragma: no cover
            return True
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            self._lock_handle.close()
            self._lock_handle = None
            return False

    def _release_file_lock(self) -> None:
        if self._lock_handle is None:
            return
        if fcntl is not None:  # pragma: no cover
            try:
                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        self._lock_handle.close()
        self._lock_handle = None

    async def start(self) -> bool:
        if self._started:
            return self._state["scheduler_enabled"]

        if not settings.PRICE_UPDATE_JOB_ENABLED:
            job_logger.info("Price update scheduler disabled by config.")
            self._started = True
            self._state["scheduler_enabled"] = False
            return False

        acquired = self._acquire_file_lock()
        if not acquired:
            job_logger.warning(
                "Scheduler not started: another process holds %s",
                LOCK_FILE,
            )
            self._started = True
            self._state["scheduler_enabled"] = False
            return False

        self.scheduler.add_job(
            self._run_daily_job,
            trigger="cron",
            hour=max(0, min(settings.PRICE_UPDATE_CRON_HOUR_UTC, 23)),
            minute=0,
            id="daily_price_update",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        self._started = True
        self._state["scheduler_enabled"] = True
        job_logger.info("Price update scheduler started (daily 06:00 UTC).")
        return True

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self._release_file_lock()
        self._started = False
        self._state["scheduler_enabled"] = False
        job_logger.info("Price update scheduler stopped.")

    async def _run_daily_job(self) -> Dict[str, Any]:
        return await self._run_update_job(
            source="scheduled",
            limit=max(1, min(settings.PRICE_UPDATE_BATCH_SIZE, 50)),
            delay_seconds=max(0.0, settings.PRICE_UPDATE_DELAY_SECONDS),
        )

    async def _run_update_job(
        self,
        *,
        source: str,
        limit: int,
        delay_seconds: float,
    ) -> Dict[str, Any]:
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")
        if limit > settings.PRICE_UPDATE_MAX_DAILY_CALLS:
            raise ValueError("limit exceeds configured Kroger daily call budget")
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")

        if self._run_lock.locked():
            snapshot = self.get_status()
            return {
                "status": "skipped",
                "reason": "A price update job is already running.",
                "snapshot": snapshot,
            }

        async with self._run_lock:
            started_at = datetime.now(timezone.utc)
            self._state["running"] = True
            self._state["last_run_started_at"] = started_at.isoformat()
            self._state["last_run_source"] = source

            db = SessionLocal()
            processed = 0
            updated = 0
            failed = 0
            errors: list[dict[str, Any]] = []

            try:
                products = db.query(Product).order_by(Product.id.asc()).limit(limit).all()
                processed = len(products)
                service = ProductService(db)

                for index, product in enumerate(products):
                    try:
                        await service.update_price_from_kroger(product.id)
                        updated += 1
                    except Exception as exc:  # pragma: no cover - exercised in integration
                        db.rollback()
                        failed += 1
                        errors.append(
                            {
                                "product_id": product.id,
                                "product_name": product.name,
                                "detail": str(exc),
                            }
                        )
                        job_logger.warning(
                            "Price update failed for product_id=%s: %s",
                            product.id,
                            exc,
                        )

                    if index < len(products) - 1 and delay_seconds > 0:
                        await asyncio.sleep(delay_seconds)

                finished_at = datetime.now(timezone.utc)
                result = {
                    "status": "completed",
                    "source": source,
                    "processed": processed,
                    "updated": updated,
                    "failed": failed,
                    "errors": errors,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                }
                self._state["last_run_result"] = result
                self._state["last_run_finished_at"] = finished_at.isoformat()
                job_logger.info(
                    "Price update run (%s): processed=%s updated=%s failed=%s",
                    source,
                    processed,
                    updated,
                    failed,
                )
                return result
            finally:
                self._state["running"] = False
                db.close()

    async def trigger_manual_update(
        self,
        *,
        limit: int = 10,
        delay_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        if self._current_task and not self._current_task.done():
            return {
                "status": "already_running",
                "snapshot": self.get_status(),
            }

        self._current_task = asyncio.create_task(
            self._run_update_job(source="manual", limit=limit, delay_seconds=delay_seconds)
        )
        return {
            "status": "started",
            "source": "manual",
            "limit": limit,
            "delay_seconds": delay_seconds,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_status(self) -> Dict[str, Any]:
        task_running = self._current_task is not None and not self._current_task.done()
        snapshot = dict(self._state)
        snapshot["manual_task_running"] = task_running
        snapshot["next_run_utc"] = None
        if self.scheduler.running:
            job = self.scheduler.get_job("daily_price_update")
            if job and job.next_run_time is not None:
                snapshot["next_run_utc"] = job.next_run_time.isoformat()
        return snapshot


price_update_scheduler = PriceUpdateScheduler()
