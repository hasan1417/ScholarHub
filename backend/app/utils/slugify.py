"""
Utility functions for generating URL-friendly slugs and short IDs.
"""

import re
import secrets
import string
import unicodedata
from typing import Optional


# Characters for short IDs (URL-safe, no ambiguous chars like 0/O, 1/l)
SHORT_ID_CHARS = string.ascii_lowercase + string.digits
SHORT_ID_CHARS = SHORT_ID_CHARS.replace('0', '').replace('o', '').replace('l', '').replace('1', '')


def generate_short_id(length: int = 8) -> str:
    """
    Generate a short, URL-safe unique ID.

    Uses a reduced character set to avoid ambiguous characters.
    8 chars gives ~2.8 trillion combinations (30^8).
    """
    return ''.join(secrets.choice(SHORT_ID_CHARS) for _ in range(length))


def slugify(text: str, max_length: int = 50) -> str:
    """
    Convert text to a URL-friendly slug.

    - Transliterates accented Latin characters (é → e, ñ → n, …)
    - Converts to lowercase
    - Replaces spaces and special chars with hyphens
    - Removes consecutive hyphens
    - Strips leading/trailing hyphens
    - Truncates to max_length

    Non-Latin scripts (Arabic, CJK, Cyrillic, …) cannot be meaningfully
    transliterated here; they are stripped and the caller should rely on the
    short_id suffix for a unique URL.
    """
    if not text:
        return ""

    # Normalize to decomposed form so combining marks become separate codepoints,
    # then drop the marks. This turns "Étude" into "Etude" and "déjà" into "deja".
    normalized = unicodedata.normalize('NFKD', text)
    slug = ''.join(ch for ch in normalized if not unicodedata.combining(ch))

    # Convert to lowercase
    slug = slug.lower()

    # Replace common special characters
    slug = slug.replace('&', 'and')
    slug = slug.replace('@', 'at')
    slug = slug.replace('+', 'plus')
    slug = slug.replace('ß', 'ss')
    slug = slug.replace('æ', 'ae')
    slug = slug.replace('œ', 'oe')
    slug = slug.replace('ø', 'o')
    slug = slug.replace('ð', 'd')
    slug = slug.replace('þ', 'th')
    slug = slug.replace('ł', 'l')

    # Replace any non-alphanumeric character with hyphen
    slug = re.sub(r'[^a-z0-9]+', '-', slug)

    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Strip leading/trailing hyphens
    slug = slug.strip('-')

    # Truncate to max_length, but don't cut in the middle of a word
    if len(slug) > max_length:
        slug = slug[:max_length]
        # Try to cut at last hyphen to avoid partial words
        last_hyphen = slug.rfind('-')
        if last_hyphen > max_length // 2:
            slug = slug[:last_hyphen]

    return slug


def generate_url_id(title: str, short_id: Optional[str] = None) -> str:
    """
    Generate a full URL identifier combining slug and short ID.

    Example: "Arabic Check Processing" -> "arabic-check-processing-a1b2c3d4"
    """
    slug = slugify(title)
    if short_id is None:
        short_id = generate_short_id()

    if slug:
        return f"{slug}-{short_id}"
    return short_id


def parse_url_id(url_id: str) -> tuple[Optional[str], str]:
    """
    Parse a URL identifier into slug and short_id components.

    The short_id is always the last segment after the final hyphen (8 chars).

    Returns: (slug, short_id)

    Examples:
        "arabic-check-processing-a1b2c3d4" -> ("arabic-check-processing", "a1b2c3d4")
        "a1b2c3d4" -> (None, "a1b2c3d4")
    """
    if not url_id:
        return None, ""

    # Short ID is always 8 characters at the end
    if len(url_id) <= 8:
        return None, url_id

    # Check if last segment looks like a short_id (8 alphanumeric chars)
    last_hyphen = url_id.rfind('-')
    if last_hyphen == -1:
        # No hyphen, entire string is short_id
        return None, url_id

    potential_short_id = url_id[last_hyphen + 1:]
    if len(potential_short_id) == 8 and potential_short_id.isalnum():
        slug = url_id[:last_hyphen] if last_hyphen > 0 else None
        return slug, potential_short_id

    # Doesn't match expected format, treat whole thing as short_id
    return None, url_id
