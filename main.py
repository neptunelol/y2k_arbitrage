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

from modules.database import check_existing_urls, save_listings
from modules.pricer import price_camera_listings
from modules.scraper import EXACT_SEARCH_QUERIES, GENERIC_SEARCH_QUERIES, scrape_ebay_listings
from modules.vision_ai import identify_camera_listings

# Load environment variables at script execution
load_dotenv()

# Global shutdown flag for graceful termination
SHUTDOWN_REQUESTED = False


def handle_shutdown_signal(signum: int, frame: Any) -> None:
    """Handles SIGINT and SIGTERM for graceful scheduler termination."""
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    logging.getLogger("y2k_bot").info(
        "[SCHEDULER] Shutdown signal received (signum=%s). Exiting gracefully...", signum
    )


def setup_logging(log_file: str = "logs/bot.log", level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns the 'y2k_bot' logger with stdout StreamHandler and RotatingFileHandler.
    Creates directory for log_file BEFORE initializing RotatingFileHandler to prevent FileNotFoundError.
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

        logger.propagate = False

    return logger


# Global logger instance
logger = setup_logging()


def run_generic_pipeline() -> dict[str, Any]:
    """
    Executes Generic Search Pipeline:
    Stage 1: [SCRAPER] Ingest generic listings using GENERIC_SEARCH_QUERIES
    Stage 2: [DATABASE] Early URL deduplication against Supabase
    Stage 3: [VISION] Route through Vision AI (gemini) for model & damage assessment
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
    Asynchronous dual scheduler implementation.
    - Exact pipeline runs every exact_interval minutes (default 10).
    - Generic pipeline runs every generic_interval minutes (default 60).
    - Ensures 60-minute loop does NOT block or pause the 10-minute loop.
    - Robust error handling: exceptions in one pipeline do not crash the other.
    """
    global SHUTDOWN_REQUESTED

    if once:
        logger.info("[SCHEDULER] Single execution mode (--once) active.")
        summary = run_pipeline()
        logger.info("[SCHEDULER] Single execution complete.")
        return summary

    logger.info(
        "[SCHEDULER] Starting non-blocking dual scheduler daemon. Exact interval: %d min, Generic interval: %d min.",
        exact_interval,
        generic_interval,
    )

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

    await asyncio.gather(exact_loop(), generic_loop())
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
    args = parser.parse_args()

    run_scheduler(once=args.once)


if __name__ == "__main__":
    main()
