"""Institutional library access through a user-configured proxy prefix.

Universities expose subscriptions through EZproxy (``https://<host>/login?url=``)
or the OpenAthens redirector (``https://go.openathens.net/redirector/<domain>?url=``).
The user's browser holds the library session, so ScholarHub only builds the link:
it never fetches proxied pages or handles university credentials.
"""

import logging
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)

MAX_PREFIX_LENGTH = 500
DOI_HANDLE_API = "https://doi.org/api/handles/{doi}"


class InvalidProxyPrefix(ValueError):
    pass


def normalize_proxy_prefix(prefix: str) -> str:
    """Validate a proxy prefix and return it stripped; raises InvalidProxyPrefix."""
    prefix = prefix.strip()
    if len(prefix) > MAX_PREFIX_LENGTH:
        raise InvalidProxyPrefix("Proxy prefix is too long")
    parsed = urlparse(prefix)
    if parsed.scheme != "https" or not parsed.netloc:
        raise InvalidProxyPrefix("Proxy prefix must be an https:// URL")
    if not prefix.endswith(("url=", "qurl=")):
        raise InvalidProxyPrefix(
            "Proxy prefix must end with 'url=', e.g. https://login.example.idm.oclc.org/login?url="
        )
    return prefix


def build_proxied_url(prefix: str, target_url: str) -> str:
    """Prepend the proxy prefix to a publisher URL.

    EZproxy's documented ``login?url=`` form takes the target unencoded; the
    OpenAthens redirector and EZproxy's ``qurl=`` form expect it percent-encoded.
    """
    host = urlparse(prefix).netloc.lower()
    if prefix.endswith("qurl=") or host.endswith("openathens.net"):
        return prefix + quote(target_url, safe="")
    return prefix + target_url


def normalize_doi(doi: str) -> str:
    doi = doi.strip()
    for marker in ("doi.org/", "doi:"):
        idx = doi.lower().find(marker)
        if idx != -1:
            doi = doi[idx + len(marker):]
    return doi.strip()


async def resolve_doi(doi: str) -> Optional[str]:
    """Return the publisher URL a DOI points to, using the DOI handle API.

    Library proxies only rewrite hosts they are configured for, and doi.org is
    usually not one of them, so the proxy must receive the publisher URL.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                DOI_HANDLE_API.format(doi=quote(doi, safe="/")), params={"type": "URL"}
            )
    except httpx.HTTPError as exc:
        logger.warning("DOI handle lookup failed for %s: %s", doi, exc)
        return None
    if resp.status_code != 200:
        return None
    for value in resp.json().get("values", []):
        if value.get("type") == "URL":
            url = (value.get("data") or {}).get("value")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
    return None
