#!/usr/bin/env python3
"""
University Access Debug Tool

Purpose:
- Given a DOI or URL, show what access options we can discover without storing credentials.
- Reuses existing services (UniversityProxyService, EnhancedPaperAccessService).
- Optionally consults Unpaywall for OA links if UNPAYWALL_EMAIL is configured.

Usage examples:
  python backend/scripts/university_access_debug.py --url https://www.sciencedirect.com/science/article/pii/S0893608023001234
  python backend/scripts/university_access_debug.py --doi 10.1038/s41586-023-06088-6
  python backend/scripts/university_access_debug.py --batch backend/scripts/university_samples.txt

Notes:
- This script performs network calls. Run it on a machine with access to KFUPM e-resources in a browser for the SSO steps.
- No credentials are handled or stored. The script detects likely SSO flows and prints guided steps.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import asdict
from typing import Optional, List, Dict

import aiohttp

try:
    import requests  # type: ignore
except Exception:
    requests = None  # Fallback if requests is not available

# Import app services
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.services.university_proxy_access import UniversityProxyService
from app.services.enhanced_paper_access import EnhancedPaperAccessService


def resolve_doi_to_url(doi: str, timeout: int = 6) -> Optional[str]:
    """Resolve DOI to publisher landing URL via doi.org redirect.

    Tries HEAD first, then falls back to GET if needed.
    """
    if not doi:
        return None
    if requests is None:
        return f"https://doi.org/{doi}"
    try:
        head = requests.head(
            f"https://doi.org/{doi}", allow_redirects=True, timeout=timeout,
            headers={"User-Agent": "ScholarHub/UniversityAccessDebug/1.0"},
        )
        if head.url and head.url != f"https://doi.org/{doi}":
            return head.url
        # Fallback to GET (some DOIs only redirect on GET)
        get = requests.get(
            f"https://doi.org/{doi}", allow_redirects=True, timeout=timeout,
            headers={"User-Agent": "ScholarHub/UniversityAccessDebug/1.0"},
        )
        return get.url
    except Exception:
        return f"https://doi.org/{doi}"


def unpaywall_lookup(doi: str, email: Optional[str]) -> Optional[Dict[str, object]]:
    """Look up OA info from Unpaywall if configured."""
    if not doi or not email or requests is None:
        return None
    try:
        url = f"https://api.unpaywall.org/v2/{doi}"
        r = requests.get(url, params={"email": email}, timeout=8,
                         headers={"User-Agent": "ScholarHub/UniversityAccessDebug/1.0"})
        if r.status_code == 200:
            data = r.json()
            best = data.get("best_oa_location") or {}
            return {
                "is_oa": data.get("is_oa"),
                "oa_url": best.get("url") or best.get("url_for_pdf") or best.get("url_for_landing_page"),
                "host_type": best.get("host_type"),
                "evidence": data.get("evidence"),
            }
    except Exception:
        return None
    return None


async def analyze_single(target_url: str, title_hint: str = "") -> Dict[str, object]:
    """Analyze a single URL using existing services, return a summary dict."""
    uni = UniversityProxyService()
    enhanced = EnhancedPaperAccessService()

    result: Dict[str, object] = {
        "input_url": target_url,
        "proxy_url": None,
        "university_instructions": None,
        "access": None,
        "proxy_fetch": None,
        "provider_search_urls": None,
        "timing_ms": 0.0,
    }
    t0 = time.time()

    # Generate proxy URL and instructions
    proxy_url = uni.generate_university_url(target_url)
    result["proxy_url"] = proxy_url
    result["university_instructions"] = uni.get_university_access_instructions(target_url)
    result["provider_search_urls"] = uni.build_provider_search_urls(title_hint, None)

    # Try enhanced access (direct/SSO/pdf redirects/alternatives)
    access = await enhanced.access_paper(target_url, title_hint)
    access_dict = access.model_dump()
    # Trim potentially large fields
    access_dict.pop("suggestions", None)
    result["access"] = access_dict

    # If a KFUPM proxy URL exists, fetch a brief summary of what it returns
    if proxy_url:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                start = time.time()
                async with session.get(proxy_url, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    ctype = resp.headers.get("content-type", "").lower()
                    text = ""
                    title = None
                    sso_login = None
                    # Only attempt to read HTML text (avoid large PDFs)
                    if "text/html" in ctype:
                        body = await resp.text()
                        # Extract <title>
                        import re as _re
                        m = _re.search(r"<title[^>]*>(.*?)</title>", body, _re.IGNORECASE | _re.DOTALL)
                        if m:
                            title = m.group(1).strip()[:300]
                        # Reuse our SSO detector to find shibboleth/institutional login
                        try:
                            sso_login = await enhanced._detect_sso_authentication(body, final_url)
                        except Exception:
                            sso_login = None
                        text = body[:800]
                    result["proxy_fetch"] = {
                        "status": resp.status,
                        "final_url": final_url,
                        "content_type": ctype,
                        "html_title": title,
                        "sso_login_url": sso_login,
                        "html_excerpt": text,
                        "elapsed_ms": round((time.time() - start) * 1000.0, 2)
                    }
        except Exception as e:
            result["proxy_fetch"] = {"error": str(e)}

    result["timing_ms"] = round((time.time() - t0) * 1000.0, 2)
    return result


async def main_async(args) -> int:
    email = os.getenv("UNPAYWALL_EMAIL")
    out: List[Dict[str, object]] = []
    targets: List[str] = []

    if args.url:
        targets.append(args.url)
    if args.doi:
        url = resolve_doi_to_url(args.doi)
        if url:
            targets.append(url)
    if args.batch:
        with open(args.batch, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith("10."):
                    url = resolve_doi_to_url(line)
                    if url:
                        targets.append(url)
                else:
                    targets.append(line)

    # De-duplicate while preserving order
    seen = set()
    deduped = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            deduped.append(t)

    if not deduped:
        print("No targets to analyze. Provide --url, --doi, or --batch.")
        return 1

    for t in deduped:
        entry: Dict[str, object] = {"target": t}
        # Optional Unpaywall OA
        if args.with_unpaywall and email:
            doi = None
            if t.startswith("https://doi.org/"):
                doi = t.split("https://doi.org/")[-1]
            if doi:
                entry["unpaywall"] = unpaywall_lookup(doi, email)

        try:
            entry["analysis"] = await analyze_single(t)
        except Exception as e:
            entry["error"] = str(e)
        out.append(entry)

    # Pretty print JSON result
    import json as _json
    print(_json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="KFUPM University Access Debug Tool")
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--url", help="Paper URL (publisher landing page)")
    g.add_argument("--doi", help="DOI, e.g., 10.1038/s41586-023-06088-6")
    p.add_argument("--batch", help="Path to a file with URLs/DOIs (one per line)")
    p.add_argument("--with-unpaywall", action="store_true", help="Lookup OA info via Unpaywall if configured")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
