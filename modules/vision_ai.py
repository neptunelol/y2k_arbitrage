"""
Module 2: Brain of Operation (Vision-Language Model Camera Identification)
Uses Google Gemini API for multimodal camera identification and damage assessment.
"""

import json
import logging
import os
import re
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


def is_placeholder_credential(val: str | None) -> bool:
    """Check if an API key string is missing, empty, or a placeholder."""
    if not val:
        return True
    val_clean = val.strip().lower()
    return val_clean.startswith("your_") or "your_" in val_clean or val_clean == ""


def create_fallback_enrichment(listing: dict[str, Any], reason: str = "VLM processing unavailable") -> dict[str, Any]:
    """Return graceful fallback enrichment for a listing."""
    title = listing.get("title", "")
    return {
        **listing,
        "identified_model": title if title else "Unknown Camera",
        "confidence_score": 0.0,
        "damage_severity": "none",
        "damage_notes": f"Fallback: {reason}",
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
        identified_model = fallback_title or "Unknown Camera"

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
    model_name: str = "gemini-2.0-flash",
) -> dict[str, Any]:
    """Process a single listing through Gemini VLM enforcing max 3 images."""
    from google.genai import types

    image_urls = listing.get("image_urls") or []
    if not isinstance(image_urls, list):
        image_urls = []

    # Enforce passing at most the first 3 image URLs
    target_images = image_urls[:3]

    title = listing.get("title", "")
    seller_desc = listing.get("seller_description", "")
    price = listing.get("price", 0.0)

    user_text = f"Listing Title: {title}\nAsking Price: ${price}\nSeller Description: {seller_desc}"

    # Build multimodal content parts for Gemini
    content_parts: list[Any] = []

    # Add image URLs directly via Part.from_uri (no downloading/base64)
    for img_url in target_images:
        if isinstance(img_url, str) and (img_url.startswith("http://") or img_url.startswith("https://")):
            try:
                content_parts.append(types.Part.from_uri(file_uri=img_url, mime_type="image/jpeg"))
            except Exception as img_exc:
                logger.warning("Failed to create image part for URL '%s': %s", img_url, img_exc)

    # Add the text prompt
    content_parts.append(user_text)

    try:
        response = client.models.generate_content(
            model=model_name,
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
        logger.warning("VLM request failed for '%s': %s", title, exc)
        return create_fallback_enrichment(listing, reason=f"VLM error: {exc}")


def identify_camera_listings(
    listings: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    model_name: str = "gemini-2.0-flash",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Primary importable callable function for Vision AI identification.
    Uses Google Gemini API for multimodal camera identification.
    Returns (filtered_for_pricer, all_enriched_for_db).
    """
    if not listings:
        logger.info("No listings provided to identify_camera_listings. Returning ([], []).")
        return ([], [])

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

    for listing in listings:
        enriched = _identify_single_listing(listing, client, model_name=model_name)
        all_enriched.append(enriched)

        if str(enriched.get("damage_severity", "")).strip().lower() == "major":
            logger.info("Filtered listing '%s' from pricer list due to major damage.", listing.get("title"))
        else:
            filtered_for_pricer.append(enriched)

    return (filtered_for_pricer, all_enriched)
