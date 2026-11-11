from __future__ import annotations

import re
from typing import Optional, Tuple

QUALITY_RANK = {
    # Tier 0-9: Camera / Screener / Pre-release
    "cam": 0,
    "camrip": 0,
    "hdcam": 1,
    "ts": 2,
    "telesync": 2,
    "hdts": 3,
    "tc": 4,
    "telecine": 4,
    "scr": 5,
    "screener": 5,
    "dvdscr": 5,
    # Tier 10-19: Standard Definition
    "sd": 10,
    "dvd": 11,
    "dvdrip": 12,
    # Tier 20-29: High Definition 720p
    "hd": 20,
    "hdtv": 21,
    "720p": 22,
    "720": 22,
    # Tier 30-39: Full High Definition / WEB-DL / 1080p
    "webrip": 30,
    "web-dl": 31,
    "webdl": 31,
    "1080p": 32,
    "1080": 32,
    "fhd": 32,
    # Tier 40-49: BluRay
    "bluray": 40,
    "bdrip": 41,
    "brrip": 41,
    # Tier 50-59: 4K UHD
    "4k": 50,
    "2160p": 50,
    "uhd": 50,
}

CANONICAL_DISPLAY = {
    "cam": "CAM",
    "camrip": "CAM",
    "hdcam": "HDCAM",
    "ts": "TS",
    "telesync": "TS",
    "hdts": "HDTS",
    "tc": "TC",
    "telecine": "TC",
    "scr": "SCR",
    "screener": "SCR",
    "dvdscr": "DVDSCR",
    "sd": "SD",
    "dvd": "DVD",
    "dvdrip": "DVDRip",
    "hd": "HD",
    "hdtv": "HDTV",
    "720p": "720p",
    "720": "720p",
    "webrip": "WEBRip",
    "web-dl": "WEB-DL",
    "webdl": "WEB-DL",
    "1080p": "1080p",
    "1080": "1080p",
    "fhd": "1080p",
    "bluray": "BluRay",
    "bdrip": "BDRip",
    "brrip": "BRRip",
    "4k": "4K",
    "2160p": "4K",
    "uhd": "4K UHD",
}

NON_QUALITY_DESCRIPTORS = {
    "hindi", "punjabi", "gujarati", "bengali", "marathi", "tamil", "telugu",
    "malayalam", "pakistani", "18+", "dual audio", "english", "dubbed",
    "south", "bollywood", "hollywood", "org", "clean"
}


def parse_quality_tier(raw: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """
    Extract a normalized quality tier and canonical display name from a raw string.
    Returns (None, None) if the input is a language descriptor or unranked.
    """
    if not raw:
        return None, None
    clean = re.sub(r"[^\w\s-]", "", raw).strip().lower()
    if clean in NON_QUALITY_DESCRIPTORS:
        return None, None

    # Exact match first
    if clean in QUALITY_RANK:
        return QUALITY_RANK[clean], CANONICAL_DISPLAY[clean]

    # Substring search for canonical tags in descending order of specificity
    for tag in ("2160p", "4k", "1080p", "web-dl", "webdl", "webrip", "bluray", "bdrip", "brrip", "720p", "hdcam", "hdts", "dvdscr", "telesync", "camrip", "hdtv", "dvdrip", "cam", "ts", "tc", "scr", "dvd", "sd", "hd"):
        if re.search(rf"\b{re.escape(tag)}\b", clean):
            return QUALITY_RANK[tag], CANONICAL_DISPLAY[tag]

    return None, None


def is_quality_upgrade(old_quality: Optional[str], new_quality: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Determine if new_quality represents a genuine, verified quality upgrade over old_quality.
    Returns (True, "CAM → HD") if new_tier > old_tier.
    Returns (False, None) for routine refreshes, identical tiers, downgrades, or invalid descriptors.
    """
    old_tier, old_disp = parse_quality_tier(old_quality)
    new_tier, new_disp = parse_quality_tier(new_quality)

    # Both must be recognized, valid quality tiers
    if old_tier is None or new_tier is None or old_disp is None or new_disp is None:
        return False, None

    # Must be strictly higher tier
    if new_tier > old_tier:
        badge = f"{old_disp} → {new_disp}"
        return True, badge

    return False, None

