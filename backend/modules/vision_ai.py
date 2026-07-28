"""
Module 2: Brain of Operation (Vision-Language Model Camera Identification)
Uses Google Gemini API for multimodal camera identification and damage assessment.
Includes automatic 429 rate-limit retries, model fallbacks, and throttling.
"""

import json
import logging
import os
import re
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

VLM_SYSTEM_PROMPT = """You are an expert vintage digital camera appraiser and technical visual diagnostician specializing in Y2K-era point-and-shoot digital cameras (e.g., Sony Cyber-shot, Canon PowerShot, Nikon Coolpix, Olympus Stylus, Fujifilm FinePix).

Your task is to inspect the attached listing images (up to 3 images) and listing text (title and seller description) to:
1. Identify the exact manufacturer make and model (e.g., "Sony Cyber-shot DSC-T700"). If the exact model cannot be determined, provide the best candidate make & model based on visual features and title text.
2. Evaluate physical damage severity into strictly ONE of three categories: "major", "minor", or "none".
   - "major": cracked LCD screen, battery compartment corrosion/rust, water damage/condensation, missing or broken lens element, crushed frame, unclosable battery door latch.
   - "minor": cosmetic scratches, scuffs, worn paint/lettering, sticker residue, missing non-essential accessories (missing charger, missing SD card, missing wrist strap, missing box).
   - "none": no visible scratches, scuffs, cracks, rust, or damage.
3. Provide concise damage notes describing visible condition or defects.
4. Assign a numerical confidence score between 0.0 and 1.0 reflecting your certainty.

You MUST respond strictly with a valid JSON object matching this structure:
{
  "identified_model": "<string>",
  "damage_severity": "major" | "minor" | "none",
  "damage_notes": "<string>",
  "confidence_score": <float 0.0 to 1.0>
}"""

FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-flash-latest", "gemini-flash-lite-latest"]


def is_placeholder_credential(val: str | None) -> bool:
    """Check if an API key string is missing, empty, or a placeholder."""
    if not val:
        return True
    val_clean = val.strip().lower()
    return val_clean.startswith("your_") or "your_" in val_clean or val_clean == ""


def extract_model_from_title(title: str) -> str:
    """Intelligently parse camera make/model from listing title as a smart fallback."""
    if not title:
        return "Unknown Camera"

    # Common camera brand patterns
    brands = [
        "Canon PowerShot", "Canon IXY", "Canon Digital IXUS", "Canon EOS",
        "Sony Cyber-shot", "Sony Cybershot", "Sony Mavica",
        "Nikon COOLPIX", "Nikon Coolpix",
        "Olympus Stylus", "Olympus FE", "Olympus CAMEDIA", "Olympus TRIP", "Olympus D-",
        "Fujifilm FinePix", "Fuji Finepix", "Fujifilm MX-", "Fujifilm DS-",
        "Kodak EasyShare", "Kodak CX", "Kodak C875", "Kodak C813",
        "Panasonic Lumix", "Pentax IQZoom", "Ricoh R", "Casio Exilim", "Vivitar ViviCam"
    ]

    title_clean = title.strip()
    for brand in brands:
        if brand.lower() in title_clean.lower():
            # Try to extract brand + model code following it
            match = re.search(re.escape(brand) + r'\s+([A-Za-z0-9\-\.]+)', title_clean, re.IGNORECASE)
            if match:
                return f"{brand} {match.group(1)}"
            return brand

    return title_clean.split("-")[0].strip() or title_clean


def create_fallback_enrichment(listing: dict[str, Any], reason: str = "VLM processing unavailable") -> dict[str, Any]:
    """Return graceful fallback enrichment for a listing."""
    title = listing.get("title", "")
    smart_model = extract_model_from_title(title)
    return {
        **listing,
        "identified_model": smart_model,
        "confidence_score": 0.5 if smart_model != "Unknown Camera" else 0.0,
        "damage_severity": "none",
        "damage_notes": f"Fallback ({reason}): Identified from listing title",
    }


def parse_vlm_json_response(raw_response_text: str, fallback_title: str = "Unknown Camera") -> dict[str, Any]:
    """
    Parses raw response string from VLM into structured dictionary.
    Handles raw JSON strings, markdown ```json ... ``` blocks, missing keys, and invalid types.
    """
    text = (raw_response_text or "").strip()
    data: dict[str, Any] = {}

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            data = json.loads(json_str)
        except Exception:
            data = {}

    identified_model = str(data.get("identified_model", "")).strip()
    if not identified_model:
        identified_model = extract_model_from_title(fallback_title)

    damage_severity = str(data.get("damage_severity", "")).strip().lower()
    if damage_severity not in ("major", "minor", "none"):
        damage_severity = "none"

    damage_notes = str(data.get("damage_notes", "")).strip()
    if not damage_notes:
        damage_notes = "No specific damage notes provided."

    try:
        confidence_score = float(data.get("confidence_score", 0.5))
        confidence_score = max(0.0, min(1.0, confidence_score))
    except (ValueError, TypeError):
        confidence_score = 0.5

    return {
        "identified_model": identified_model,
        "damage_severity": damage_severity,
        "damage_notes": damage_notes,
        "confidence_score": confidence_score,
    }


def _identify_single_listing(
    listing: dict[str, Any],
    client: Any,
    model_name: str = "gemini-3.6-flash",
    max_retries: int = 2,
) -> dict[str, Any]:
    """Process a single listing through Gemini VLM with rate-limit retries and model fallbacks."""
    from google.genai import types

    image_urls = listing.get("image_urls") or []
    if not isinstance(image_urls, list):
        image_urls = []

    target_images = image_urls[:3]
    title = listing.get("title", "")
    seller_desc = listing.get("seller_description", "")
    price = listing.get("price", 0.0)

    user_text = f"Listing Title: {title}\nAsking Price: ${price}\nSeller Description: {seller_desc}"
    content_parts: list[Any] = []

    for img_url in target_images:
        if isinstance(img_url, str) and (img_url.startswith("http://") or img_url.startswith("https://")):
            try:
                content_parts.append(types.Part.from_uri(file_uri=img_url, mime_type="image/jpeg"))
            except Exception as img_exc:
                logger.warning("Failed to create image part for URL '%s': %s", img_url, img_exc)

    content_parts.append(user_text)

    # Models to try if 429 quota occurs
    models_to_try = [model_name] + [m for m in FALLBACK_MODELS if m != model_name]

    last_error = None
    for current_model in models_to_try:
        for attempt in range(max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=current_model,
                    contents=content_parts,
                    config=types.GenerateContentConfig(
                        system_instruction=VLM_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        max_output_tokens=300,
                        temperature=0.2,
                    ),
                )
                raw_text = response.text
                parsed = parse_vlm_json_response(raw_text, fallback_title=title)

                return {
                    **listing,
                    "identified_model": parsed["identified_model"],
                    "confidence_score": parsed["confidence_score"],
                    "damage_severity": parsed["damage_severity"],
                    "damage_notes": parsed["damage_notes"],
                }
            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    # Check for explicit retry delay hint in error message
                    retry_match = re.search(r"retry in ([0-9\.]+)s", err_str, re.IGNORECASE)
                    wait_time = float(retry_match.group(1)) if retry_match else (2.0 ** attempt + 1.0)
                    wait_time = min(wait_time, 10.0) # cap wait at 10s per item to avoid hanging pipeline
                    
                    if attempt < max_retries:
                        logger.warning(
                            "Rate limited (429) on %s for '%s'. Retrying in %.1fs (attempt %d/%d)...",
                            current_model, title[:30], wait_time, attempt + 1, max_retries
                        )
                        time.sleep(wait_time)
                    else:
                        logger.warning("Quota exhausted on %s for '%s', trying fallback model...", current_model, title[:30])
                        break
                else:
                    logger.warning("VLM request failed on %s for '%s': %s", current_model, title[:30], exc)
                    break

    # If all models/retries failed, use smart title-extracted model fallback
    return create_fallback_enrichment(listing, reason=f"VLM Quota Exceeded ({last_error})")


def _identify_single_listing_anthropic(
    listing: dict[str, Any],
    client: Any,
    model_name: str = "claude-3-5-sonnet-20241022",
    max_retries: int = 2,
) -> dict[str, Any]:
    """Process a single listing through Anthropic VLM with top 3 image URLs."""
    image_urls = listing.get("image_urls") or []
    if not isinstance(image_urls, list):
        image_urls = []

    target_images = image_urls[:3]
    title = listing.get("title", "")
    seller_desc = listing.get("seller_description", "")
    price = listing.get("price", 0.0)

    user_text = f"Listing Title: {title}\nAsking Price: ${price}\nSeller Description: {seller_desc}"
    content_parts: list[dict[str, Any]] = []

    for img_url in target_images:
        if isinstance(img_url, str) and (img_url.startswith("http://") or img_url.startswith("https://")):
            content_parts.append({
                "type": "image",
                "source": {
                    "type": "url",
                    "url": img_url,
                }
            })

    content_parts.append({"type": "text", "text": user_text})

    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=model_name,
                max_tokens=300,
                system=VLM_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content_parts}],
            )
            raw_text = ""
            if hasattr(response, "content") and response.content and len(response.content) > 0:
                raw_text = getattr(response.content[0], "text", "")
            parsed = parse_vlm_json_response(raw_text, fallback_title=title)

            return {
                **listing,
                "identified_model": parsed["identified_model"],
                "confidence_score": parsed["confidence_score"],
                "damage_severity": parsed["damage_severity"],
                "damage_notes": parsed["damage_notes"],
            }
        except Exception as exc:
            logger.warning("Anthropic VLM request failed on attempt %d for '%s': %s", attempt + 1, title[:30], exc)
            if attempt < max_retries:
                time.sleep(1.0)

    return create_fallback_enrichment(listing, reason="Anthropic VLM processing failed")


def identify_camera_listings(
    listings: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    model_name: str = "gemini-3.6-flash",
    throttle_seconds: float = 1.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Primary importable callable function for Vision AI identification.
    Supports Google Gemini API or Anthropic Claude API based on VLM_PROVIDER.
    Returns (filtered_for_pricer, all_enriched_for_db).
    """
    if not listings:
        logger.info("No listings provided to identify_camera_listings. Returning ([], []).")
        return ([], [])

    vlm_provider = os.getenv("VLM_PROVIDER", "gemini").strip().lower()

    if vlm_provider in ("claude", "anthropic"):
        resolved_api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if is_placeholder_credential(resolved_api_key):
            logger.warning("ANTHROPIC_API_KEY is missing or placeholder. Returning fallback enrichment.")
            all_enriched = [create_fallback_enrichment(item, reason="Missing or placeholder API key") for item in listings]
            filtered_for_pricer = [item for item in all_enriched if str(item.get("damage_severity", "")).strip().lower() != "major"]
            return (filtered_for_pricer, all_enriched)

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=resolved_api_key)
        except Exception as exc:
            logger.warning("Failed to instantiate Anthropic client: %s", exc)
            all_enriched = [create_fallback_enrichment(item, reason=f"Client init error: {exc}") for item in listings]
            filtered_for_pricer = [item for item in all_enriched if str(item.get("damage_severity", "")).strip().lower() != "major"]
            return (filtered_for_pricer, all_enriched)

        claude_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        all_enriched = []
        filtered_for_pricer = []

        total = len(listings)
        for idx, listing in enumerate(listings):
            enriched = _identify_single_listing_anthropic(listing, client, model_name=claude_model)
            all_enriched.append(enriched)

            if str(enriched.get("damage_severity", "")).strip().lower() == "major":
                logger.info("Filtered listing '%s' from pricer list due to major damage.", listing.get("title"))
            else:
                filtered_for_pricer.append(enriched)

            if idx < total - 1 and throttle_seconds > 0:
                time.sleep(throttle_seconds)

        return (filtered_for_pricer, all_enriched)

    resolved_api_key = api_key or os.getenv("GEMINI_API_KEY")

    if is_placeholder_credential(resolved_api_key):
        logger.warning("GEMINI_API_KEY is missing or placeholder. Returning fallback enrichment.")
        all_enriched = [create_fallback_enrichment(item, reason="Missing or placeholder API key") for item in listings]
        filtered_for_pricer = [item for item in all_enriched if str(item.get("damage_severity", "")).strip().lower() != "major"]
        return (filtered_for_pricer, all_enriched)

    try:
        from google import genai
        client = genai.Client(api_key=resolved_api_key)
    except Exception as exc:
        logger.warning("Failed to instantiate Gemini client: %s", exc)
        all_enriched = [create_fallback_enrichment(item, reason=f"Client init error: {exc}") for item in listings]
        filtered_for_pricer = [item for item in all_enriched if str(item.get("damage_severity", "")).strip().lower() != "major"]
        return (filtered_for_pricer, all_enriched)

    all_enriched = []
    filtered_for_pricer = []

    total = len(listings)
    for idx, listing in enumerate(listings):
        enriched = _identify_single_listing(listing, client, model_name=model_name)
        all_enriched.append(enriched)

        if str(enriched.get("damage_severity", "")).strip().lower() == "major":
            logger.info("Filtered listing '%s' from pricer list due to major damage.", listing.get("title"))
        else:
            filtered_for_pricer.append(enriched)

        # Small throttle delay between items to respect Gemini RPM (Requests Per Minute) limits
        if idx < total - 1 and throttle_seconds > 0:
            time.sleep(throttle_seconds)

    return (filtered_for_pricer, all_enriched)

