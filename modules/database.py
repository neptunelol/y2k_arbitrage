"""
Module 4: Supabase Database Connector & Dashboard Data Sync
"""

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger(__name__)


def is_placeholder_credential(url: str | None = None, key: str | None = None) -> bool:
    """Check if Supabase credentials are missing or set to placeholder values."""
    if url is None:
        url = os.getenv("SUPABASE_URL", "")
    if key is None:
        key = os.getenv("SUPABASE_KEY", "")

    if not url or not key:
        return True

    url_lower = str(url).strip().lower()
    key_lower = str(key).strip().lower()

    placeholders = [
        "your-supabase",
        "your_supabase",
        "your_anon_key",
        "your_service_role_key",
        "https://your-supabase-project.supabase.co",
        "your_supabase_anon_or_service_role_key",
    ]

    if any(p in url_lower for p in placeholders) or any(p in key_lower for p in placeholders):
        return True

    if key_lower.startswith("your_"):
        return True

    return False


def get_supabase_client() -> Client | None:
    """Initialize and return Supabase client, or None if credentials missing/placeholder."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")

    if is_placeholder_credential(url, key):
        logger.warning("Supabase credentials missing or set to placeholder values. Database client disabled.")
        return None

    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


def format_listing_for_db(listing: dict[str, Any]) -> dict[str, Any]:
    """Format and normalize a listing dictionary for Supabase database table insertion."""
    raw_url = listing.get("listing_url") if listing.get("listing_url") is not None else listing.get("url")
    url = raw_url if raw_url is not None else ""
    title = listing.get("title")
    model_name = listing.get("model_name") if listing.get("model_name") is not None else listing.get("identified_model")

    def to_float(val: Any) -> float | None:
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    raw_asking = listing.get("asking_price") if listing.get("asking_price") is not None else listing.get("price")
    asking_price = to_float(raw_asking)
    confidence_score = to_float(listing.get("confidence_score"))

    damage_severity = str(listing.get("damage_severity") or "none").lower()
    damage_notes = listing.get("damage_notes")

    # Major damage null handling rules:
    if damage_severity == "major":
        market_value = None
        profit_margin = None
        is_profitable_deal = False
    else:
        raw_market = (
            listing.get("market_value")
            if listing.get("market_value") is not None
            else listing.get("estimated_market_value")
        )
        market_value = to_float(raw_market)
        profit_margin = to_float(listing.get("profit_margin"))

        raw_is_profitable = listing.get("is_profitable_deal", False)
        if isinstance(raw_is_profitable, str):
            is_profitable_deal = raw_is_profitable.strip().lower() in ("true", "1")
        else:
            is_profitable_deal = raw_is_profitable in (True, 1)

    raw_images = listing.get("image_urls")
    if raw_images is None:
        image_urls = []
    elif isinstance(raw_images, list):
        image_urls = raw_images
    elif isinstance(raw_images, str):
        try:
            parsed = json.loads(raw_images)
            image_urls = parsed if isinstance(parsed, list) else [raw_images]
        except Exception:
            image_urls = [raw_images]
    else:
        image_urls = []

    db_record: dict[str, Any] = {
        "listing_url": str(url).strip(),
        "title": str(title) if title is not None else None,
        "model_name": str(model_name) if model_name is not None else None,
        "asking_price": asking_price,
        "market_value": market_value,
        "profit_margin": profit_margin,
        "is_profitable_deal": is_profitable_deal,
        "confidence_score": confidence_score,
        "damage_severity": damage_severity,
        "damage_notes": str(damage_notes) if damage_notes is not None else None,
        "image_urls": image_urls,
    }

    if "created_at" in listing and listing["created_at"] is not None:
        db_record["created_at"] = listing["created_at"]

    return db_record


def check_existing_urls(urls: list[str], client: Client | None = None) -> set[str]:
    """Query existing listing_urls from Supabase database in 100-item chunks. Return set of existing URLs."""
    if not urls:
        return set()

    if client is None:
        client = get_supabase_client()

    if client is None:
        return set()

    existing_urls: set[str] = set()
    valid_urls = [str(u).strip() for u in urls if u and isinstance(u, str) and str(u).strip()]
    if not valid_urls:
        return set()

    chunk_size = 100
    for i in range(0, len(valid_urls), chunk_size):
        chunk = valid_urls[i : i + chunk_size]
        try:
            res = client.table("listings").select("listing_url").in_("listing_url", chunk).execute()
            if res and hasattr(res, "data") and res.data:
                for row in res.data:
                    if isinstance(row, dict) and row.get("listing_url"):
                        existing_urls.add(row["listing_url"])
        except Exception as e:
            logger.error(f"Error checking existing URLs in database for chunk: {e}")

    return existing_urls


def save_listings(listings: list[dict[str, Any]], client: Client | None = None) -> dict[str, int]:
    """Persist listings to Supabase database.

    Performs alias mapping, major damage null handling, deduplication (intra-batch and DB),
    and bulk insert with dry-run fallback.

    Returns:
        dict: {"inserted": int, "skipped": int, "failed": int}
    """
    if not listings:
        return {"inserted": 0, "skipped": 0, "failed": 0}

    inserted = 0
    skipped = 0
    failed = 0

    seen_urls: set[str] = set()
    valid_payloads: list[dict[str, Any]] = []

    # Intra-batch validation and deduplication
    for item in listings:
        if not isinstance(item, dict):
            failed += 1
            continue

        url = item.get("listing_url") if item.get("listing_url") is not None else item.get("url")
        if not url or not isinstance(url, str) or not url.strip():
            failed += 1
            continue

        clean_url = url.strip()
        if clean_url in seen_urls:
            skipped += 1
            continue

        try:
            formatted_record = format_listing_for_db(item)
            seen_urls.add(clean_url)
            valid_payloads.append(formatted_record)
        except Exception as exc:
            logger.warning(f"Failed to format listing for DB: {exc}")
            failed += 1
            continue

    if client is None:
        client = get_supabase_client()

    # Dry-run fallback mode if client is None
    if client is None:
        logger.warning("Supabase client unavailable. Dry-run fallback active.")
        return {
            "inserted": 0,
            "skipped": skipped + len(valid_payloads),
            "failed": failed,
        }

    if not valid_payloads:
        return {"inserted": 0, "skipped": skipped, "failed": failed}

    # Database deduplication
    urls_to_check = [record["listing_url"] for record in valid_payloads]
    db_existing_urls = check_existing_urls(urls_to_check, client=client)

    candidate_payloads: list[dict[str, Any]] = []
    for record in valid_payloads:
        if record["listing_url"] in db_existing_urls:
            skipped += 1
        else:
            candidate_payloads.append(record)

    if not candidate_payloads:
        return {"inserted": 0, "skipped": skipped, "failed": failed}

    # Bulk Insert with single-row fallback
    try:
        res = client.table("listings").insert(candidate_payloads).execute()
        if res and hasattr(res, "data") and res.data is not None:
            inserted_count = len(res.data)
            inserted += inserted_count
            if inserted_count < len(candidate_payloads):
                failed += len(candidate_payloads) - inserted_count
        else:
            inserted += len(candidate_payloads)
    except Exception as e:
        logger.error(f"Bulk insert failed: {e}. Falling back to single-row inserts.")
        for payload in candidate_payloads:
            try:
                single_res = client.table("listings").insert(payload).execute()
                if single_res and hasattr(single_res, "data") and single_res.data is not None:
                    inserted += 1
                else:
                    inserted += 1
            except Exception as single_err:
                logger.error(f"Single-row insert failed for {payload.get('listing_url')}: {single_err}")
                failed += 1

    return {
        "inserted": inserted,
        "skipped": skipped,
        "failed": failed,
    }

