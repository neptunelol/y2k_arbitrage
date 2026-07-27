"""
Module 1: Data Ingestion (eBay Browse API Scraper)
"""

import base64
import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv

# Load environment variables at top of module
load_dotenv()

logger = logging.getLogger(__name__)

# Hardcoded fallback list of 10 search query terms
DEFAULT_SEARCH_QUERIES: list[str] = [
    "Old silver camera",
    "Untested digital camera",
    "Vintage point and shoot",
    "Digital camera lot",
    "Old camera estate sale",
    "Retro digital camera",
    "Early digital camera",
    "Y2K camera",
    "Old compact camera",
    "Grandma camera digital",
]


def is_placeholder_credential(val: str | None) -> bool:
    """Check if a credential string is missing, empty, or a placeholder."""
    if not val:
        return True
    val_clean = val.strip().lower()
    return val_clean.startswith("your_") or "your_ebay" in val_clean or val_clean == ""


def get_ebay_endpoints(environment: str | None) -> tuple[str, str]:
    """
    Return (token_url, browse_base_url) for eBay API endpoints.
    Toggles between sandbox and production based on environment parameter or env var.
    """
    env_clean = (environment or os.getenv("EBAY_ENVIRONMENT", "sandbox")).strip().lower()
    if env_clean == "production":
        token_url = "https://api.ebay.com/identity/v1/oauth2/token"
        browse_base_url = "https://api.ebay.com"
    else:
        token_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        browse_base_url = "https://api.sandbox.ebay.com"
    return token_url, browse_base_url


def fetch_oauth_token(app_id: str, cert_id: str, token_url: str) -> str | None:
    """
    Fetch OAuth 2.0 Client Credentials token from eBay identity endpoint.
    Returns access token string or None on failure.
    """
    try:
        credentials = f"{app_id}:{cert_id}"
        encoded_auth = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }
        response = requests.post(token_url, headers=headers, data=data, timeout=10)
        if response.status_code != 200:
            logger.warning(
                "Failed to acquire eBay OAuth token. Status: %s, Response: %s",
                response.status_code,
                response.text,
            )
            return None
        payload = response.json()
        return payload.get("access_token")
    except Exception as exc:
        logger.error("Exception occurred during eBay OAuth token fetch: %s", exc)
        return None


def scrape_ebay_listings(
    queries: list[str] | None = None,
    max_results: int | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    """
    Scrapes eBay item summaries using eBay Browse API.

    :param queries: Optional list of search terms. Defaults to 10 fallback query terms.
    :param max_results: Optional limit per query. Defaults to MAX_RESULTS_PER_QUERY env var (default 5).
    :param environment: Optional environment ("sandbox" or "production"). Defaults to EBAY_ENVIRONMENT env var.
    :return: Deduplicated list of listing dicts matching the schema:
             title (str), url (str), price (float), image_urls (list[str]), seller_description (str).
    """
    if queries is None:
        queries = DEFAULT_SEARCH_QUERIES

    if max_results is None:
        raw_max = os.getenv("MAX_RESULTS_PER_QUERY", "5")
        try:
            max_results = int(raw_max)
        except (ValueError, TypeError):
            max_results = 5
    else:
        try:
            max_results = int(max_results)
        except (ValueError, TypeError):
            max_results = 5

    app_id = os.getenv("EBAY_APP_ID")
    cert_id = os.getenv("EBAY_CERT_ID")

    if is_placeholder_credential(app_id) or is_placeholder_credential(cert_id):
        logger.warning(
            "eBay credentials (EBAY_APP_ID / EBAY_CERT_ID) are missing or set to placeholder values. Returning empty listings list []."
        )
        return []

    token_url, browse_base_url = get_ebay_endpoints(environment)
    access_token = fetch_oauth_token(app_id, cert_id, token_url)

    if not access_token:
        logger.warning("Could not obtain valid eBay access token. Returning [].")
        return []

    search_url = f"{browse_base_url}/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }

    deduplicated_listings: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for query in queries:
        params = {
            "q": query,
            "limit": max_results,
        }
        try:
            response = requests.get(search_url, headers=headers, params=params, timeout=10)
            if response.status_code != 200:
                logger.warning(
                    "Browse API search failed for query '%s' with status %s",
                    query,
                    response.status_code,
                )
                continue

            data = response.json()
            item_summaries = data.get("itemSummaries", [])

            for item in item_summaries:
                url = item.get("itemWebUrl") or item.get("itemHref", "")
                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)
                title = str(item.get("title") or "")

                # Extract price
                price_val = 0.0
                price_obj = item.get("price")
                if isinstance(price_obj, dict) and "value" in price_obj:
                    try:
                        price_val = float(price_obj["value"])
                    except (ValueError, TypeError):
                        price_val = 0.0

                # Extract image URLs
                image_urls: list[str] = []
                primary_image = (item.get("image") or {}).get("imageUrl")
                if primary_image and isinstance(primary_image, str):
                    image_urls.append(primary_image)

                additional_images = item.get("additionalImages") or []
                if isinstance(additional_images, list):
                    for img in additional_images:
                        if isinstance(img, dict):
                            img_url = img.get("imageUrl")
                            if img_url and isinstance(img_url, str) and img_url not in image_urls:
                                image_urls.append(img_url)

                seller_description = str(item.get("shortDescription") or item.get("condition") or "")

                listing_dict: dict[str, Any] = {
                    "title": title,
                    "url": url,
                    "price": price_val,
                    "image_urls": image_urls,
                    "seller_description": seller_description,
                }
                deduplicated_listings.append(listing_dict)

        except Exception as exc:
            logger.warning("Error fetching eBay listings for query '%s': %s", query, exc)
            continue

    return deduplicated_listings


# Alias export for compatibility
fetch_ebay_listings = scrape_ebay_listings
