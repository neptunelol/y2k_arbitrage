"""
Main Orchestrator Script for Y2K Camera Arbitrage Bot
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

from dotenv import load_dotenv

from modules.database import check_existing_urls, save_listings
from modules.pricer import price_camera_listings
from modules.scraper import scrape_ebay_listings
from modules.vision_ai import identify_camera_listings

# Load environment variables at script execution
load_dotenv()

# Global shutdown flag for graceful termination
SHUTDOWN_REQUESTED = False


def handle_shutdown_signal(signum: int, frame: Any) -> None:
    """Handles SIGINT and SIGTERM for graceful scheduler termination."""
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    logging.getLogger("y2k_bot").info("[SCHEDULER] Shutdown signal received (signum=%s). Exiting gracefully...", signum)


def setup_logging(log_file: str = "logs/bot.log", level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns the 'y2k_bot' logger with stdout StreamHandler and RotatingFileHandler.
    Creates directory for log_file before creating handlers to prevent FileNotFoundError.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("y2k_bot")
    logger.setLevel(level)

    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Console StreamHandler (stdout)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        # RotatingFileHandler (1MB per file, 5 backup files, UTF-8)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1048576,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.propagate = True

    return logger


# Global logger instance
logger = setup_logging()


def get_eastern_now() -> datetime:
    """Returns current datetime in US Eastern Time."""
    try:
        import zoneinfo
        return datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-5)))


def is_peak_hour(dt: datetime | None = None) -> bool:
    """
    Returns True if the specified or current US Eastern time falls within peak hours.
    Reads PEAK_START_HOUR (default 8) and PEAK_END_HOUR (default 23) from env vars.
    """
    try:
        peak_start = int(os.getenv("PEAK_START_HOUR", "8"))
    except ValueError:
        peak_start = 8

    try:
        peak_end = int(os.getenv("PEAK_END_HOUR", "23"))
    except ValueError:
        peak_end = 23

    if dt is None:
        dt = get_eastern_now()

    hour = dt.hour
    if peak_start <= peak_end:
        return peak_start <= hour <= peak_end
    else:
        return hour >= peak_start or hour <= peak_end


def calculate_seconds_until_peak(now_et: datetime, peak_start: int) -> float:
    """Calculates sleep duration in seconds until next PEAK_START_HOUR ET."""
    target_dt = datetime(
        year=now_et.year,
        month=now_et.month,
        day=now_et.day,
        hour=peak_start,
        minute=0,
        second=0,
        microsecond=0,
        tzinfo=now_et.tzinfo
    )
    if now_et >= target_dt:
        target_dt += timedelta(days=1)
    return max(1.0, (target_dt - now_et).total_seconds())


def interruptible_sleep(seconds: float) -> bool:
    """
    Sleeps in 1-second increments, monitoring SHUTDOWN_REQUESTED.
    Returns True if interrupted by shutdown signal, False otherwise.
    """
    global SHUTDOWN_REQUESTED
    elapsed = 0.0
    while elapsed < seconds:
        if SHUTDOWN_REQUESTED:
            return True
        sleep_chunk = min(1.0, seconds - elapsed)
        time.sleep(sleep_chunk)
        elapsed += sleep_chunk
    return False


def run_pipeline() -> dict[str, Any]:
    """
    Executes a single end-to-end pipeline run:
    Stage 1: [SCRAPER] Scrape eBay listings
    Stage 2: [DATABASE] Early deduplication (filter out existing URLs before Vision AI)
    Stage 3: [VISION] Vision AI camera model identification & major damage filtering
    Stage 4: [PRICER] Market comp pricing and profit margin calculation
    Stage 5: [DATABASE] Merge priced listings into enriched dataset and persist to Supabase
    """
    logger.info("=== Starting Pipeline Run ===")
    summary = {
        "status": "success",
        "scraped": 0,
        "new_items": 0,
        "processed": 0,
        "priced": 0,
        "profitable": 0,
        "inserted": 0,
        "skipped": 0,
        "failed": 0
    }

    # Stage 1: [SCRAPER]
    scraped_listings: list[dict[str, Any]] = []
    try:
        logger.info("[SCRAPER] Ingesting listings from eBay Browse API...")
        scraped_listings = scrape_ebay_listings()
        scraped_count = len(scraped_listings) if scraped_listings else 0
        summary["scraped"] = scraped_count
        logger.info("[SCRAPER] Scraped %d unique listings.", scraped_count)
    except Exception as exc:
        logger.error("[SCRAPER] Failed during scraping stage: %s", exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = f"[SCRAPER] {exc}"
        return summary

    if not scraped_listings:
        logger.warning("[SCRAPER] No listings scraped. Ending pipeline run early.")
        return summary

    # Stage 2: [DATABASE] Early Deduplication
    new_items: list[dict[str, Any]] = []
    try:
        logger.info("[DATABASE] Performing early URL deduplication check against Supabase...")
        urls = [item["url"] for item in scraped_listings if isinstance(item, dict) and item.get("url")]
        existing_urls = check_existing_urls(urls)
        new_items = [item for item in scraped_listings if isinstance(item, dict) and item.get("url") not in existing_urls]
        skipped_count = len(scraped_listings) - len(new_items)
        summary["new_items"] = len(new_items)
        logger.info(
            "[DATABASE] Checked %d scraped URLs. Found %d existing (skipped). %d new listings remaining for processing.",
            len(urls),
            skipped_count,
            len(new_items)
        )
    except Exception as exc:
        logger.error("[DATABASE] Failed during deduplication check: %s", exc, exc_info=True)
        new_items = scraped_listings
        summary["new_items"] = len(new_items)

    if not new_items:
        logger.info("[DATABASE] No new listings to process after deduplication. Pipeline run complete.")
        return summary

    # Stage 3: [VISION] Vision AI identification
    filtered_for_pricer: list[dict[str, Any]] = []
    all_enriched: list[dict[str, Any]] = []
    try:
        logger.info("[VISION] Running Vision AI model identification and damage assessment on %d items...", len(new_items))
        filtered_for_pricer, all_enriched = identify_camera_listings(new_items)
        major_damage_count = len(all_enriched) - len(filtered_for_pricer)
        summary["processed"] = len(all_enriched)
        logger.info(
            "[VISION] Identified models for %d listings. Major damage (filtered out): %d, Minor/No damage (sent to pricer): %d.",
            len(all_enriched),
            major_damage_count,
            len(filtered_for_pricer)
        )
    except Exception as exc:
        logger.error("[VISION] Failed during Vision AI stage: %s", exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = f"[VISION] {exc}"
        return summary

    # Stage 4: [PRICER] Market Pricing
    priced_listings: list[dict[str, Any]] = []
    if filtered_for_pricer:
        try:
            logger.info("[PRICER] Fetching market comps and pricing %d listings...", len(filtered_for_pricer))
            priced_listings = price_camera_listings(filtered_for_pricer)
            profitable_count = sum(
                1 for item in priced_listings if isinstance(item, dict) and item.get("is_profitable_deal") is True
            )
            summary["priced"] = len(priced_listings)
            summary["profitable"] = profitable_count
            logger.info("[PRICER] Priced %d listings. Flagged %d profitable deals.", len(priced_listings), profitable_count)
        except Exception as exc:
            logger.error("[PRICER] Failed during pricing stage: %s", exc, exc_info=True)
            priced_listings = filtered_for_pricer

    # Stage 5: [DATABASE] Merge & Persist
    try:
        logger.info("[DATABASE] Merging priced listings into enriched dataset and persisting to Supabase...")
        priced_by_url = {item["url"]: item for item in priced_listings if isinstance(item, dict) and item.get("url")}
        final_listings: list[dict[str, Any]] = []
        for item in all_enriched:
            url = item.get("url") if isinstance(item, dict) else None
            if url and url in priced_by_url:
                final_listings.append(priced_by_url[url])
            else:
                final_listings.append(item)

        save_res = save_listings(final_listings)
        summary["inserted"] = save_res.get("inserted", 0)
        summary["skipped"] = save_res.get("skipped", 0)
        summary["failed"] = save_res.get("failed", 0)
        logger.info(
            "[DATABASE] Persistence complete -> Inserted: %d, Skipped: %d, Failed: %d",
            summary["inserted"],
            summary["skipped"],
            summary["failed"]
        )
    except Exception as exc:
        logger.error("[DATABASE] Failed during save_listings stage: %s", exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = f"[DATABASE] {exc}"
        return summary

    logger.info("=== Pipeline Run Completed Successfully ===")
    return summary


def run_scheduler(once: bool = False) -> dict[str, Any] | None:
    """
    Scheduler loop. Runs pipeline periodically during peak hours (PEAK_START_HOUR to PEAK_END_HOUR ET),
    and sleeps outside peak hours until peak start time.
    If once=True, executes run_pipeline() once immediately and returns the summary dict.
    """
    global SHUTDOWN_REQUESTED

    if once:
        logger.info("[SCHEDULER] Single execution mode (--once) active.")
        summary = run_pipeline()
        logger.info("[SCHEDULER] Single execution complete.")
        return summary

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    try:
        run_hours = float(os.getenv("RUN_SCHEDULE_HOURS", "2"))
    except ValueError:
        run_hours = 2.0

    try:
        peak_start = int(os.getenv("PEAK_START_HOUR", "8"))
    except ValueError:
        peak_start = 8

    try:
        peak_end = int(os.getenv("PEAK_END_HOUR", "23"))
    except ValueError:
        peak_end = 23

    logger.info(
        "[SCHEDULER] Starting daemon loop. Peak window: %02d:00-%02d:00 ET, Interval: %.1f hours.",
        peak_start, peak_end, run_hours
    )

    while not SHUTDOWN_REQUESTED:
        now_et = get_eastern_now()
        if is_peak_hour(now_et):
            logger.info(
                "[SCHEDULER] Peak hours active (%02d:00 ET). Running pipeline...",
                now_et.hour
            )
            run_pipeline()

            sleep_sec = max(1.0, run_hours * 3600.0)
            logger.info("[SCHEDULER] Sleeping for %.2f hours until next scheduled run...", run_hours)
            if interruptible_sleep(sleep_sec):
                break
        else:
            sleep_sec = calculate_seconds_until_peak(now_et, peak_start)
            logger.info(
                "[SCHEDULER] Outside peak hours (%02d:00 ET). Sleeping until peak start at %02d:00 ET (sleeping %.2f hours)...",
                now_et.hour, peak_start, sleep_sec / 3600.0
            )
            if interruptible_sleep(sleep_sec):
                break

    logger.info("[SCHEDULER] Shutdown complete.")
    return None


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Y2K Digital Camera Arbitrage Bot Orchestrator")
    parser.add_argument("--once", action="store_true", help="Run the pipeline once and exit")
    args = parser.parse_args()

    run_scheduler(once=args.once)


if __name__ == "__main__":
    main()
