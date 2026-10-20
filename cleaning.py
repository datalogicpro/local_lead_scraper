"""Cleaning functions for the lead scraper.

Each function takes one messy value and returns a clean one,
or None when the value is missing or unusable.
"""

import re
from typing import Any, TypedDict
from urllib.parse import urlsplit, urlunsplit


class Lead(TypedDict):
    """One clean business lead, ready to save."""

    place_id: str
    name: str
    address: str | None
    phone: str | None
    website: str | None


def clean_name(name: str | None) -> str | None:
    """Trim extra spaces: '  Harbor  Drain Experts ' -> 'Harbor Drain Experts'."""
    if not name:
        return None
    return " ".join(name.split()) or None


def clean_phone(phone: str | None) -> str | None:
    """Standardize a US phone number to (954) 555-0101.

    Returns None if it is blank or is not a 10-digit number.
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]  # drop the country code
    if len(digits) != 10:
        return None
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def clean_website(url: str | None) -> str | None:
    """Standardize a website address.

    'HTTP://Site.com/?utm_source=google' -> 'http://site.com'
    Lowercases it, drops tracking parts after the '?', and removes a trailing slash.
    """
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return None
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def parse_place(place: dict[str, Any]) -> Lead:
    """Turn one place from Google's reply into a flat, clean record.

    Raises ValueError when the place has no id or no name, so the caller
    can log it and move on to the next place.
    """
    place_id = place.get("id")
    name = clean_name(place.get("displayName", {}).get("text"))
    if not place_id:
        raise ValueError("place has no id")
    if not name:
        raise ValueError(f"place {place_id} has no name")

    return {
        "place_id": place_id,
        "name": name,
        "address": clean_name(place.get("formattedAddress")),
        "phone": clean_phone(place.get("nationalPhoneNumber")),
        "website": clean_website(place.get("websiteUri")),
    }
