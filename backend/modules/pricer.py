"""
Module 3: Validator & Comps Evaluation Module (Market Pricer)
"""

import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv

from modules.scraper import fetch_oauth_token, get_ebay_endpoints, is_placeholder_credential

# Load environment variables at top of module
load_dotenv()

logger = logging.getLogger(__name__)

# Static Y2K Camera Benchmark Database (Tier 3 Fallback)
MODEL_BENCHMARKS: dict[str, float] = {
    "canon powershot sd1000": 85.00,
    "canon powershot sd1100": 90.00,
    "canon powershot g9": 120.00,
    "canon powershot g10": 130.00,
    "canon powershot a590": 55.00,
    "canon powershot": 65.00,
    "sony cyber-shot dsc-t700": 95.00,
    "sony cyber-shot dsc-w80": 70.00,
    "sony cyber-shot dsc-w55": 65.00,
    "sony cyber-shot": 60.00,
    "nikon coolpix s210": 55.00,
    "nikon coolpix l11": 45.00,
    "nikon coolpix": 50.00,
    "olympus stylus 710": 60.00,
    "olympus stylus mju": 85.00,
    "olympus stylus": 55.00,
    "fujifilm finepix z10fd": 65.00,
    "fujifilm finepix": 50.00,
}
DEFAULT_BENCHMARK_PRICE: float = 45.00


def get_min_profit_margin() -> float:
    """Read MIN_PROFIT_MARGIN environment variable with a safe default of 40.0."""
    raw_val = os.getenv("MIN_PROFIT_MARGIN", "40.0")
    try:
        return float(raw_val)
    except (ValueError, TypeError):
        logger.warning("Invalid MIN_PROFIT_MARGIN value '%s'. Defaulting to 40.0.", raw_val)
        return 40.0


def get_exact_match_margin() -> float:
    """Read EXACT_MATCH_MARGIN environment variable with a safe default of 25.0."""
    raw_val = os.getenv("EXACT_MATCH_MARGIN", "25.0")
    try:
        return float(raw_val)
    except (ValueError, TypeError):
        logger.warning("Invalid EXACT_MATCH_MARGIN value '%s'. Defaulting to 25.0.", raw_val)
        return 25.0



def extract_asking_price(listing: dict[str, Any]) -> float | None:
    """
    Safely extract asking price float from listing dictionary using 'asking_price' or 'price'.
    Returns float > 0 or None if missing or non-positive.
    """
    raw_val = listing.get("asking_price")
    if raw_val is None:
        raw_val = listing.get("price")

    if raw_val is None:
        return None

    if isinstance(raw_val, (int, float)):
        val = float(raw_val)
        return val if val > 0 else None

    if isinstance(raw_val, str):
        cleaned = raw_val.replace("$", "").replace(",", "").strip()
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except ValueError:
            return None

    return None


def calculate_market_value(sold_prices: list[float] | None) -> float | None:
    """
    Calculate average of up to 5 valid sold prices.
    Returns float rounded to 2 decimal places, or None if no valid prices.
    """
    if not sold_prices:
        return None

    valid_prices = [float(p) for p in sold_prices if isinstance(p, (int, float)) and p > 0]
    if not valid_prices:
        return None

    subset = valid_prices[:5]
    avg_price = sum(subset) / len(subset)
    return round(avg_price, 2)


def calculate_profit_margin(asking_price: float | None, market_value: float | None) -> float | None:
    """
    Calculate profit margin percentage: ((market_value - asking_price) / market_value) * 100.
    Returns rounded float, or None if asking_price or market_value are invalid/non-positive.
    """
    if asking_price is None or asking_price <= 0:
        return None
    if market_value is None or market_value <= 0:
        return None

    margin = ((market_value - asking_price) / market_value) * 100.0
    return round(margin, 2)


def get_benchmark_valuation(model_or_title: str) -> float:
    """
    Look up estimated benchmark price from Y2K model database.
    Falls back to $45.00 if no specific model key matches.
    """
    if not model_or_title:
        return DEFAULT_BENCHMARK_PRICE

    text_lower = model_or_title.lower()

    # Sort benchmark keys by length descending for best match
    sorted_benchmarks = sorted(MODEL_BENCHMARKS.items(), key=lambda x: len(x[0]), reverse=True)
    for model_key, price in sorted_benchmarks:
        if model_key in text_lower:
            return price

    return DEFAULT_BENCHMARK_PRICE


def get_estimated_market_value(
    model_or_title: str,
    environment: str | None = None,
) -> float | None:
    """
    Fetch estimated market value using a 3-tier fallback waterfall:
    1. Marketplace Insights API (/buy/marketplace_insights/v1/item_sales/search) for sold prices.
    2. Browse API (/buy/browse/v1/item_summary/search) active comps * 0.85 discount.
    3. Benchmark Y2K Camera model database ($45.00 fallback).
    """
    clean_query = (model_or_title or "").strip()
    if not clean_query:
        return DEFAULT_BENCHMARK_PRICE

    app_id = os.getenv("EBAY_APP_ID")
    cert_id = os.getenv("EBAY_CERT_ID")

    # Check credentials; if missing/placeholder, jump to Tier 3
    if is_placeholder_credential(app_id) or is_placeholder_credential(cert_id):
        return get_benchmark_valuation(clean_query)

    token_url, browse_base_url = get_ebay_endpoints(environment)
    access_token = fetch_oauth_token(app_id, cert_id, token_url)

    if not access_token:
        return get_benchmark_valuation(clean_query)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }

    # Tier 1: Marketplace Insights API (Sold Listings)
    insights_url = f"{browse_base_url}/buy/marketplace_insights/v1/item_sales/search"
    try:
        response = requests.get(
            insights_url,
            headers=headers,
            params={"q": clean_query, "limit": 5, "LH_Sold": "1", "LH_Complete": "1"},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            item_sales = data.get("itemSales") or data.get("itemSummaries") or []
            sold_prices: list[float] = []
            for item in item_sales:
                price_obj = item.get("price") or item.get("lastSoldPrice") or item.get("total")
                if isinstance(price_obj, dict) and "value" in price_obj:
                    try:
                        p_val = float(price_obj["value"])
                        if p_val > 0:
                            sold_prices.append(p_val)
                    except (ValueError, TypeError):
                        pass

            market_val = calculate_market_value(sold_prices)
            if market_val is not None:
                return market_val
    except Exception as exc:
        logger.warning("Marketplace Insights API call failed for query '%s': %s", clean_query, exc)

    # Tier 2: Browse API Active Comps with 0.85 multiplier (with LH_Sold=1&LH_Complete=1)
    browse_url = f"{browse_base_url}/buy/browse/v1/item_summary/search"
    try:
        response = requests.get(
            browse_url,
            headers=headers,
            params={"q": clean_query, "limit": 5, "filter": "conditions:{USED}", "LH_Sold": "1", "LH_Complete": "1"},
            timeout=10,
        )
        if response.status_code != 200:
            # Fallback without condition filter
            response = requests.get(
                browse_url,
                headers=headers,
                params={"q": clean_query, "limit": 5, "LH_Sold": "1", "LH_Complete": "1"},
                timeout=10,
            )

        if response.status_code == 200:
            data = response.json()
            item_summaries = data.get("itemSummaries") or []
            active_prices: list[float] = []
            for item in item_summaries:
                price_obj = item.get("price")
                if isinstance(price_obj, dict) and "value" in price_obj:
                    try:
                        p_val = float(price_obj["value"])
                        if p_val > 0:
                            active_prices.append(p_val)
                    except (ValueError, TypeError):
                        pass

            active_avg = calculate_market_value(active_prices)
            if active_avg is not None:
                return round(active_avg * 0.85, 2)
    except Exception as exc:
        logger.warning("Browse API active comps search failed for query '%s': %s", clean_query, exc)

    # Tier 3: Static Y2K Benchmark Database Lookup
    return get_benchmark_valuation(clean_query)


def price_camera_listings(
    filtered_listings: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    """
    Prices camera listings by fetching sold market comps and calculating profit margin.

    :param filtered_listings: List of camera listing dicts (e.g. from vision_ai module).
    :param api_key: Optional API key override.
    :param environment: Optional environment ("sandbox" or "production").
    :return: Retains ALL input listings (Requirement R3), enriching each with:
             - estimated_market_value (float | None)
             - profit_margin (float | None)
             - is_profitable_deal (bool)
    """
    load_dotenv()

    if filtered_listings is None:
        return []

    min_generic_margin = get_min_profit_margin()
    min_exact_margin = get_exact_match_margin()
    priced_listings: list[dict[str, Any]] = []

    for listing in filtered_listings:
        if not isinstance(listing, dict):
            continue

        item = dict(listing)
        asking_price = extract_asking_price(item)
        model_name = item.get("identified_model") or item.get("title") or ""

        market_val = get_estimated_market_value(model_name, environment=environment)
        margin = calculate_profit_margin(asking_price, market_val)

        search_type = item.get("search_type", "generic")
        min_margin = min_exact_margin if search_type == "exact" else min_generic_margin

        is_profitable = False
        if margin is not None and margin >= min_margin:
            is_profitable = True

        item["estimated_market_value"] = market_val
        item["profit_margin"] = margin
        item["is_profitable_deal"] = is_profitable

        priced_listings.append(item)

    return priced_listings
