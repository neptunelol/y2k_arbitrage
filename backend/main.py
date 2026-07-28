"""
Main Orchestrator Script for Y2K Camera Arbitrage Bot
Dual-Track Pipeline & Non-Blocking Dual-Frequency Scheduler (Requirement R6)
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
os.makedirs(os.path.join(SCRIPT_DIR, "logs"), exist_ok=True)

from modules.database import check_existing_urls, save_listings
from modules.pricer import price_camera_listings
from modules.scraper import EXACT_SEARCH_QUERIES, GENERIC_SEARCH_QUERIES, scrape_ebay_listings
from modules.vision_ai import identify_camera_listings

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables at script execution
load_dotenv()

# Global shutdown flag for graceful termination
SHUTDOWN_REQUESTED = False


def is_blank_or_placeholder(val: str | None) -> bool:
    if not val:
        return True
    val_clean = val.strip().lower()
    if not val_clean:
        return True
    placeholders = [
        "your_",
        "your-supabase",
        "your_supabase",
        "your_anon_key",
        "your_service_role_key",
        "https://your-supabase-project.supabase.co",
        "your_ebay_app_id",
        "your_ebay_cert_id",
        "your_gemini_api_key",
        "your_anthropic_api_key",
    ]
    return any(p in val_clean for p in placeholders)


def validate_environment() -> None:
    """
    Validates early that required environment variables are set and non-empty/non-placeholder.
    Checks EBAY_APP_ID, EBAY_CERT_ID, GEMINI_API_KEY (or ANTHROPIC_API_KEY), SUPABASE_URL, SUPABASE_KEY.
    If any are missing or blank, writes error message to sys.stderr and calls sys.exit(1).
    """
    load_dotenv()
    required_vars = [
        ("EBAY_APP_ID", os.getenv("EBAY_APP_ID")),
        ("EBAY_CERT_ID", os.getenv("EBAY_CERT_ID")),
        ("SUPABASE_URL", os.getenv("SUPABASE_URL")),
        ("SUPABASE_KEY", os.getenv("SUPABASE_KEY")),
    ]
    missing = []
    for name, val in required_vars:
        if is_blank_or_placeholder(val):
            missing.append(name)

    gemini_key = os.getenv("GEMINI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if is_blank_or_placeholder(gemini_key) and is_blank_or_placeholder(anthropic_key):
        missing.append("GEMINI_API_KEY or ANTHROPIC_API_KEY")

    if missing:
        sys.stderr.write(
            f"FATAL ERROR: Environment validation failed. Missing or blank required environment variable(s): {', '.join(missing)}\n"
            f"Please configure your .env file with valid credentials.\n"
        )
        sys.stderr.flush()
        sys.exit(1)


def handle_shutdown_signal(signum: int, frame: Any) -> None:
    """Handles SIGINT and SIGTERM for graceful scheduler termination."""
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    logging.getLogger("y2k_bot").info(
        "[SCHEDULER] Shutdown signal received (signum=%s). Exiting gracefully...", signum
    )


def setup_logging(log_file: str | None = None, level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns the 'y2k_bot' logger with stdout StreamHandler and RotatingFileHandler.
    Creates directory for log_file BEFORE initializing RotatingFileHandler to prevent FileNotFoundError.
    """
    if not log_file:
        log_file = os.path.join(SCRIPT_DIR, "logs", "bot.log")

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

        logger.propagate = False

    return logger


# Global logger instance
logger = setup_logging()

# FastAPI Application for on-demand trigger endpoints
app = FastAPI(title="Y2K Camera Arbitrage Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Y2K Arbitrage Bot API"}


@app.api_route("/api/scan/fast", methods=["GET", "POST", "OPTIONS"])
async def scan_fast(background_tasks: BackgroundTasks):
    """Trigger Fast-Track scan (Exact match pipeline) on demand in background."""
    logger.info("[FASTAPI] Fast-Track scan triggered via API.")
    background_tasks.add_task(run_exact_pipeline)
    return {
        "status": "success",
        "search_type": "exact",
        "message": "Fast-Track scan initiated in background."
    }


@app.api_route("/api/scan/slow", methods=["GET", "POST", "OPTIONS"])
async def scan_slow(background_tasks: BackgroundTasks):
    """Trigger Slow-Track scan (Generic VLM pipeline) on demand in background."""
    logger.info("[FASTAPI] Slow-Track scan triggered via API.")
    background_tasks.add_task(run_generic_pipeline)
    return {
        "status": "success",
        "search_type": "generic",
        "message": "Slow-Track scan initiated in background."
    }


def run_generic_pipeline() -> dict[str, Any]:
    """
    Executes Generic Search Pipeline:
    Stage 1: [SCRAPER] Ingest generic listings using GENERIC_SEARCH_QUERIES
    Stage 2: [DATABASE] Early URL deduplication against Supabase
    Stage 3: [VISION] Route through Vision AI (gemini/claude) for model & damage assessment
    Stage 4: [PRICER] Price non-major listings using MIN_PROFIT_MARGIN (40%)
    Stage 5: [DATABASE] Merge dataset and persist to Supabase
    """
    logger.info("=== [SCHEDULER] Starting Generic Pipeline Run ===")
    summary: dict[str, Any] = {
        "status": "success",
        "search_type": "generic",
        "scraped": 0,
        "new_items": 0,
        "processed": 0,
        "priced": 0,
        "profitable": 0,
        "inserted": 0,
        "skipped": 0,
        "failed": 0,
    }

    # Stage 1: [SCRAPER]
    scraped_listings: list[dict[str, Any]] = []
    try:
        logger.info("[SCRAPER] Ingesting generic listings from eBay Browse API...")
        scraped_listings = scrape_ebay_listings(queries=GENERIC_SEARCH_QUERIES, search_type="generic")
        scraped_count = len(scraped_listings) if scraped_listings else 0
        summary["scraped"] = scraped_count
        logger.info("[SCRAPER] Scraped %d generic listings.", scraped_count)
    except Exception as exc:
        logger.error("[SCRAPER] Failed during generic scraping stage: %s", exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = f"[SCRAPER] {exc}"
        return summary

    if not scraped_listings:
        logger.warning("[SCRAPER] No generic listings scraped. Ending pipeline run early.")
        return summary

    # Stage 2: [DATABASE] Early Deduplication
    new_items: list[dict[str, Any]] = []
    try:
        logger.info("[DATABASE] Performing early URL deduplication check against Supabase...")
        urls = [item["url"] for item in scraped_listings if isinstance(item, dict) and item.get("url")]
        existing_urls = check_existing_urls(urls)
        new_items = [
            item for item in scraped_listings if isinstance(item, dict) and item.get("url") not in existing_urls
        ]
        skipped_count = len(scraped_listings) - len(new_items)
        summary["new_items"] = len(new_items)
        summary["skipped"] = skipped_count
        logger.info(
            "[DATABASE] Checked %d scraped URLs. Found %d existing (skipped). %d new generic listings remaining.",
            len(urls),
            skipped_count,
            len(new_items),
        )
    except Exception as exc:
        logger.error("[DATABASE] Failed during deduplication check: %s", exc, exc_info=True)
        new_items = scraped_listings
        summary["new_items"] = len(new_items)

    if not new_items:
        logger.info("[DATABASE] No new generic listings to process after deduplication.")
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
            len(filtered_for_pricer),
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
        summary["skipped"] = summary["skipped"] + save_res.get("skipped", 0)
        summary["failed"] = save_res.get("failed", 0)
        logger.info(
            "[DATABASE] Persistence complete -> Inserted: %d, Skipped: %d, Failed: %d",
            summary["inserted"],
            summary["skipped"],
            summary["failed"],
        )
    except Exception as exc:
        logger.error("[DATABASE] Failed during save_listings stage: %s", exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = f"[DATABASE] {exc}"
        return summary

    logger.info("=== [SCHEDULER] Generic Pipeline Run Completed Successfully ===")
    return summary


def run_exact_pipeline() -> dict[str, Any]:
    """
    Executes Exact Search Pipeline:
    Stage 1: [SCRAPER] Ingest exact model listings using EXACT_SEARCH_QUERIES
    Stage 2: [DATABASE] Early URL deduplication against Supabase
    Stage 3: [ROUTING CONDITIONAL] SKIP vision_ai.py entirely! Route directly to pricer.
    Stage 4: [PRICER] Price listings directly using EXACT_MATCH_MARGIN (25%)
    Stage 5: [DATABASE] Persist priced exact listings to Supabase
    """
    logger.info("=== [SCHEDULER] Starting Exact Pipeline Run ===")
    summary: dict[str, Any] = {
        "status": "success",
        "search_type": "exact",
        "scraped": 0,
        "new_items": 0,
        "processed": 0,
        "priced": 0,
        "profitable": 0,
        "inserted": 0,
        "skipped": 0,
        "failed": 0,
    }

    # Stage 1: [SCRAPER]
    scraped_listings: list[dict[str, Any]] = []
    try:
        logger.info("[SCRAPER] Ingesting exact model listings from eBay Browse API...")
        scraped_listings = scrape_ebay_listings(queries=EXACT_SEARCH_QUERIES, search_type="exact")
        scraped_count = len(scraped_listings) if scraped_listings else 0
        summary["scraped"] = scraped_count
        logger.info("[SCRAPER] Scraped %d exact model listings.", scraped_count)
    except Exception as exc:
        logger.error("[SCRAPER] Failed during exact scraping stage: %s", exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = f"[SCRAPER] {exc}"
        return summary

    if not scraped_listings:
        logger.warning("[SCRAPER] No exact listings scraped. Ending exact pipeline run early.")
        return summary

    # Stage 2: [DATABASE] Early Deduplication
    new_items: list[dict[str, Any]] = []
    try:
        logger.info("[DATABASE] Performing early URL deduplication check against Supabase...")
        urls = [item["url"] for item in scraped_listings if isinstance(item, dict) and item.get("url")]
        existing_urls = check_existing_urls(urls)
        new_items = [
            item for item in scraped_listings if isinstance(item, dict) and item.get("url") not in existing_urls
        ]
        skipped_count = len(scraped_listings) - len(new_items)
        summary["new_items"] = len(new_items)
        summary["skipped"] = skipped_count
        logger.info(
            "[DATABASE] Checked %d scraped exact URLs. Found %d existing (skipped). %d new listings remaining.",
            len(urls),
            skipped_count,
            len(new_items),
        )
    except Exception as exc:
        logger.error("[DATABASE] Failed during deduplication check: %s", exc, exc_info=True)
        new_items = scraped_listings
        summary["new_items"] = len(new_items)

    if not new_items:
        logger.info("[DATABASE] No new exact listings to process after deduplication.")
        return summary

    # Stage 3 & 4: [ROUTING CONDITIONAL & PRICER] Skip Vision AI and route directly to Pricer
    logger.info(
        "[PRICER] [ROUTING CONDITIONAL] Skipping Vision AI module for exact match listings. Routing %d items directly to Pricer...",
        len(new_items),
    )
    priced_listings: list[dict[str, Any]] = []
    try:
        priced_listings = price_camera_listings(new_items)
        profitable_count = sum(
            1 for item in priced_listings if isinstance(item, dict) and item.get("is_profitable_deal") is True
        )
        summary["priced"] = len(priced_listings)
        summary["profitable"] = profitable_count
        logger.info("[PRICER] Priced %d exact listings. Flagged %d profitable deals.", len(priced_listings), profitable_count)
    except Exception as exc:
        logger.error("[PRICER] Failed during exact pricing stage: %s", exc, exc_info=True)
        priced_listings = new_items

    # Stage 5: [DATABASE] Persist exact listings
    try:
        logger.info("[DATABASE] Persisting exact listings to Supabase...")
        save_res = save_listings(priced_listings)
        summary["inserted"] = save_res.get("inserted", 0)
        summary["skipped"] = summary["skipped"] + save_res.get("skipped", 0)
        summary["failed"] = save_res.get("failed", 0)
        logger.info(
            "[DATABASE] Persistence complete -> Inserted: %d, Skipped: %d, Failed: %d",
            summary["inserted"],
            summary["skipped"],
            summary["failed"],
        )
    except Exception as exc:
        logger.error("[DATABASE] Failed during exact save_listings stage: %s", exc, exc_info=True)
        summary["status"] = "error"
        summary["error"] = f"[DATABASE] {exc}"
        return summary

    logger.info("=== [SCHEDULER] Exact Pipeline Run Completed Successfully ===")
    return summary


def run_pipeline() -> dict[str, Any]:
    """
    Executes sequential pipeline run of both exact and generic pipelines.
    Used for single-run mode (--once) or end-to-end integration execution.
    """
    logger.info("=== Starting Unified Pipeline Run (Exact + Generic) ===")
    exact_summary = run_exact_pipeline()
    generic_summary = run_generic_pipeline()

    combined_summary = {
        "status": "success" if exact_summary.get("status") == "success" and generic_summary.get("status") == "success" else "error",
        "exact": exact_summary,
        "generic": generic_summary,
        "scraped": exact_summary.get("scraped", 0) + generic_summary.get("scraped", 0),
        "new_items": exact_summary.get("new_items", 0) + generic_summary.get("new_items", 0),
        "processed": generic_summary.get("processed", 0),
        "priced": exact_summary.get("priced", 0) + generic_summary.get("priced", 0),
        "profitable": exact_summary.get("profitable", 0) + generic_summary.get("profitable", 0),
        "inserted": exact_summary.get("inserted", 0) + generic_summary.get("inserted", 0),
        "skipped": exact_summary.get("skipped", 0) + generic_summary.get("skipped", 0),
        "failed": exact_summary.get("failed", 0) + generic_summary.get("failed", 0),
    }
    return combined_summary


async def run_scheduler_async(
    once: bool = False,
    exact_interval: int = 10,
    generic_interval: int = 60,
) -> dict[str, Any] | None:
    """
    Asynchronous dual scheduler implementation using APScheduler AsyncIOScheduler.
    - Fast-Track (exact) pipeline runs every exact_interval minutes (default 10).
    - Slow-Track (generic) pipeline runs every generic_interval minutes (default 60).
    - Ensures 60-minute loop does NOT block or pause the 10-minute loop.
    """
    global SHUTDOWN_REQUESTED

    if once:
        logger.info("[SCHEDULER] Single execution mode (--once) active.")
        summary = run_pipeline()
        logger.info("[SCHEDULER] Single execution complete.")
        return summary

    logger.info(
        "[SCHEDULER] Starting non-blocking dual scheduler daemon with AsyncIOScheduler. Fast-track interval: %d min, Slow-track interval: %d min.",
        exact_interval,
        generic_interval,
    )

    scheduler = AsyncIOScheduler()
    try:
        scheduler.add_job(run_exact_pipeline, 'interval', minutes=exact_interval, id='fast_track_scan', replace_existing=True)
        scheduler.add_job(run_generic_pipeline, 'interval', minutes=generic_interval, id='slow_track_scan', replace_existing=True)
        scheduler.start()
    except Exception as exc:
        logger.warning("[SCHEDULER] APScheduler initialization warning: %s", exc)

    async def exact_loop():
        logger.info("[SCHEDULER] Initialized Exact match loop (interval: %d min)", exact_interval)
        while not SHUTDOWN_REQUESTED:
            try:
                run_exact_pipeline()
            except Exception as exc:
                logger.error("[SCHEDULER] Uncaught exception in exact loop: %s", exc, exc_info=True)

            sleep_seconds = exact_interval * 60
            for _ in range(sleep_seconds):
                if SHUTDOWN_REQUESTED:
                    break
                await asyncio.sleep(1)

    async def generic_loop():
        logger.info("[SCHEDULER] Initialized Generic match loop (interval: %d min)", generic_interval)
        while not SHUTDOWN_REQUESTED:
            try:
                run_generic_pipeline()
            except Exception as exc:
                logger.error("[SCHEDULER] Uncaught exception in generic loop: %s", exc, exc_info=True)

            sleep_seconds = generic_interval * 60
            for _ in range(sleep_seconds):
                if SHUTDOWN_REQUESTED:
                    break
                await asyncio.sleep(1)

    try:
        await asyncio.gather(exact_loop(), generic_loop())
    finally:
        if scheduler.running:
            scheduler.shutdown()
        logger.info("[SCHEDULER] Non-blocking scheduler loop stopped cleanly.")
    return None


def run_scheduler(
    once: bool = False,
    exact_interval: int | None = None,
    generic_interval: int | None = None,
) -> dict[str, Any] | None:
    """
    Entry point to trigger the non-blocking dual scheduler daemon or a single --once run.
    """
    if exact_interval is None:
        try:
            exact_interval = int(os.getenv("EXACT_INTERVAL_MINUTES", "10"))
        except ValueError:
            exact_interval = 10

    if generic_interval is None:
        try:
            generic_interval = int(os.getenv("GENERIC_INTERVAL_MINUTES", "60"))
        except ValueError:
            generic_interval = 60

    if once:
        return asyncio.run(run_scheduler_async(once=True, exact_interval=exact_interval, generic_interval=generic_interval))

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    try:
        return asyncio.run(run_scheduler_async(once=False, exact_interval=exact_interval, generic_interval=generic_interval))
    except (KeyboardInterrupt, SystemExit):
        logger.info("[SCHEDULER] Interrupted by signal. Shutting down daemon...")
        return None


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="eBay Y2K Camera Arbitrage Bot Orchestrator")
    parser.add_argument("--once", "-o", action="store_true", help="Run one pass of exact and generic pipelines and exit")
    parser.add_argument("--loop", "-l", action="store_true", help="Run non-blocking dual scheduler daemon (default)")
    parser.add_argument("--server", "-s", action="store_true", help="Start FastAPI web server")
    args = parser.parse_args()

    validate_environment()

    if args.server:
        import uvicorn
        port = int(os.getenv("PORT", "8000"))
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        run_scheduler(once=args.once)


if __name__ == "__main__":
    main()
