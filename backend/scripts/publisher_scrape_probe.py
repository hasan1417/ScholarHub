#!/usr/bin/env python3
"""
Publisher Scrape Probe (OA‑only, ToS‑aware)

Goal:
- Probe 5 common publishers (IEEE Xplore, SpringerLink, ScienceDirect, Wiley, ACM DL)
- For a DOI or URL, resolve to the landing page and attempt to extract content ONLY if:
  - Unpaywall indicates Open Access, and
  - robots.txt allows crawling of the target path
- If not OA or disallowed by robots, report and skip (use institutional access instead).

Notes:
- This is a diagnostic tool; it does NOT bypass paywalls or store credentials.
- For institutional content, prefer your KFUPM proxy flow and in‑browser SSO.
- For robust PDF parsing, integrate GROBID or science‑parse; here we use PyPDF2 as a light fallback.

Usage:
  python backend/scripts/publisher_scrape_probe.py --doi 10.1000/xyz123 --with-unpaywall
  python backend/scripts/publisher_scrape_probe.py --url https://link.springer.com/article/10.xxxx
  python backend/scripts/publisher_scrape_probe.py --batch backend/scripts/publisher_samples.txt --with-unpaywall
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import aiohttp
from urllib.parse import urlparse, urljoin
import urllib.robotparser as robotparser

try:
    import requests  # type: ignore
except Exception:
    requests = None

try:
    from PyPDF2 import PdfReader  # type: ignore
except Exception:
    PdfReader = None  # Optional; script will handle gracefully


PUBLISHER_WHITELIST = {
    'ieeexplore.ieee.org': 'IEEE Xplore',
    'link.springer.com': 'SpringerLink',
    'www.sciencedirect.com': 'ScienceDirect',
    'onlinelibrary.wiley.com': 'Wiley Online Library',
    'dl.acm.org': 'ACM Digital Library',
}


def resolve_doi(doi: str, timeout: int = 8) -> Optional[str]:
    if not doi:
        return None
    if requests is None:
        return f"https://doi.org/{doi}"
    headers = {"User-Agent": "ScholarHub/ScrapeProbe/1.0"}
    try:
        r = requests.head(f"https://doi.org/{doi}", allow_redirects=True, timeout=timeout, headers=headers)
        if r.url and r.ok:
            return r.url
        r = requests.get(f"https://doi.org/{doi}", allow_redirects=True, timeout=timeout, headers=headers)
        return r.url
    except Exception:
        return f"https://doi.org/{doi}"


def unpaywall_is_oa(doi: str, email: Optional[str]) -> Tuple[bool, Optional[str]]:
    if not doi or not email or requests is None:
        return False, None
    try:
        r = requests.get(f"https://api.unpaywall.org/v2/{doi}", params={"email": email}, timeout=10,
                         headers={"User-Agent": "ScholarHub/ScrapeProbe/1.0"})
        if r.status_code == 200:
            data = r.json()
            best = data.get('best_oa_location') or {}
            return bool(data.get('is_oa')), best.get('url') or best.get('url_for_pdf') or best.get('url_for_landing_page')
    except Exception:
        pass
    return False, None


async def allowed_by_robots(session: aiohttp.ClientSession, url: str, ua: str = "ScholarHubBot") -> bool:
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        async with session.get(robots_url, timeout=8) as resp:
            if resp.status != 200:
                return True  # be conservative; many sites don’t serve robots
            content = await resp.text()
        rp = robotparser.RobotFileParser()
        rp.parse(content.splitlines())
        return rp.can_fetch(ua, url)
    except Exception:
        return True


def detect_pdf_links(html: str, base_url: str) -> List[str]:
    links: List[str] = []
    for m in re.finditer(r"href=\"([^\"]+\.pdf)([^\"]*)\"", html, re.IGNORECASE):
        href = m.group(1)
        if not href.startswith('http'):
            href = urljoin(base_url, href)
        links.append(href)
    # also common patterns
    for pat in [r"href=\"([^\"]*download[^\"]*pdf[^\"]*)\"", r"href=\"([^\"]*fulltext[^\"]*pdf[^\"]*)\""]:
        for m in re.finditer(pat, html, re.IGNORECASE):
            href = m.group(1)
            if not href.startswith('http'):
                href = urljoin(base_url, href)
            if href not in links:
                links.append(href)
    return links[:5]


def extract_pdf_text(pdf_bytes: bytes, max_pages: int = 3) -> str:
    if PdfReader is None:
        return ""
    try:
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = min(len(reader.pages), max_pages)
        out = []
        for i in range(pages):
            try:
                out.append(reader.pages[i].extract_text() or "")
            except Exception:
                continue
        return "\n".join(out)[:4000]
    except Exception:
        return ""


async def fetch_text(session: aiohttp.ClientSession, url: str) -> Tuple[int, str, str]:
    async with session.get(url) as resp:
        status = resp.status
        ctype = resp.headers.get('content-type', '').lower()
        text = await resp.text(errors='ignore') if 'text/html' in ctype or 'text/' in ctype else ''
        return status, ctype, text


async def fetch_pdf(session: aiohttp.ClientSession, url: str, limit_mb: int = 10) -> Tuple[int, bytes]:
    async with session.get(url) as resp:
        status = resp.status
        if status != 200:
            return status, b''
        data = await resp.read()
        if len(data) > limit_mb * 1024 * 1024:
            data = data[:limit_mb * 1024 * 1024]
        return status, data


async def probe_one(target: str, title: Optional[str], email: Optional[str]) -> Dict[str, object]:
    t0 = time.time()
    out: Dict[str, object] = {"target": target, "resolved": None, "publisher": None, "result": {}}
    timeout = aiohttp.ClientTimeout(total=15)
    headers = {"User-Agent": "ScholarHub/ScrapeProbe/1.0"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        url = target
        doi = None
        if target.lower().startswith('10.'):
            doi = target
            url = resolve_doi(target) or f"https://doi.org/{target}"
        elif target.startswith('https://doi.org/'):
            doi = target.split('https://doi.org/')[-1]
        out["resolved"] = url

        host = urlparse(url).netloc.lower()
        publisher = PUBLISHER_WHITELIST.get(host)
        out["publisher"] = publisher or host

        # Check OA via Unpaywall (if DOI)
        is_oa, oa_url = unpaywall_is_oa(doi, email) if doi else (False, None)
        out['result']['is_oa'] = is_oa
        if oa_url:
            out['result']['oa_url'] = oa_url

        if not publisher:
            out['result']['note'] = 'Publisher not in whitelist; skipping fetch.'
            out['elapsed_ms'] = round((time.time() - t0) * 1000.0, 2)
            return out

        # Respect robots
        if not await allowed_by_robots(session, url):
            out['result']['note'] = 'robots.txt disallows crawling this URL.'
            out['elapsed_ms'] = round((time.time() - t0) * 1000.0, 2)
            return out

        # If not OA, do not attempt PDF fetch (report and exit)
        if not is_oa:
            status, ctype, html = await fetch_text(session, url)
            out['result'].update({
                'status': status,
                'content_type': ctype,
                'message': 'Likely paywalled; OA not indicated. Use institutional access.'
            })
            out['elapsed_ms'] = round((time.time() - t0) * 1000.0, 2)
            return out

        # OA path: attempt to discover PDF link, fetch, and extract first pages of text
        status, ctype, html = await fetch_text(session, url)
        pdf_links = []
        if 'text/html' in ctype and html:
            pdf_links = detect_pdf_links(html, url)
        # If Unpaywall provided an OA URL, prefer it
        if oa_url:
            pdf_links = [oa_url] + [l for l in pdf_links if l != oa_url]

        text_excerpt = ''
        pdf_status = None
        if pdf_links:
            pdf_status, pdf_bytes = await fetch_pdf(session, pdf_links[0])
            if pdf_status == 200 and pdf_bytes:
                text_excerpt = extract_pdf_text(pdf_bytes)

        out['result'].update({
            'status': status,
            'content_type': ctype,
            'pdf_candidates': pdf_links[:3],
            'pdf_fetch_status': pdf_status,
            'text_excerpt': text_excerpt[:1000] if text_excerpt else ''
        })
        out['elapsed_ms'] = round((time.time() - t0) * 1000.0, 2)
        return out


async def main_async(args) -> int:
    email = os.getenv('UNPAYWALL_EMAIL') if args.with_unpaywall else None
    targets: List[str] = []
    if args.url:
        targets.append(args.url)
    if args.doi:
        targets.append(args.doi)
    if args.batch:
        with open(args.batch, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    targets.append(line)

    if not targets:
        print('Provide --url, --doi, or --batch')
        return 1

    out: List[Dict[str, object]] = []
    for t in targets:
        try:
            res = await probe_one(t, args.title, email)
        except Exception as e:
            res = {"target": t, "error": str(e)}
        out.append(res)

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Publisher Scrape Probe (OA‑only)')
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument('--url', help='Publisher URL')
    g.add_argument('--doi', help='DOI, e.g., 10.1038/s41586-023-06088-6')
    p.add_argument('--batch', help='Path to file with URLs/DOIs (one per line)')
    p.add_argument('--title', help='Optional title (unused in probe, reserved for future)')
    p.add_argument('--with-unpaywall', action='store_true', help='Consult Unpaywall for OA detection')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())

