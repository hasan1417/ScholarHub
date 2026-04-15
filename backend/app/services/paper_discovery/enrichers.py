"""Metadata enrichers used during discovery."""

from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp

from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.interfaces import PaperEnricher
from app.services.paper_discovery.models import DiscoveredPaper

logger = logging.getLogger(__name__)

class CrossrefEnricher(PaperEnricher):
    """Enrich papers using Crossref API"""
    
    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig):
        self.session = session
        self.config = config
    
    async def enrich(self, papers: List[DiscoveredPaper]) -> None:
        """Enrich papers with Crossref metadata"""
        if not papers:
            return
        
        sem = asyncio.Semaphore(self.config.max_concurrent_enrichments)
        
        async def enrich_single(paper: DiscoveredPaper):
            async with sem:
                try:
                    if not paper.doi:
                        return
                    
                    url = f"https://api.crossref.org/works/{paper.doi}"
                    async with self.session.get(url) as resp:
                        if resp.status != 200:
                            return
                        
                        data = await resp.json()
                        item = data.get('message', {})
                        
                        # Update missing fields
                        if not paper.journal and item.get('container-title'):
                            paper.journal = item['container-title'][0]
                        
                        if not paper.year and item.get('published-print'):
                            try:
                                paper.year = item['published-print']['date-parts'][0][0]
                            except (KeyError, IndexError):
                                pass
                        
                        if paper.citations_count is None:
                            paper.citations_count = item.get('is-referenced-by-count')
                        
                        if not paper.url and item.get('URL'):
                            paper.url = item['URL']

                        # Crossref sometimes has a JATS-wrapped abstract that
                        # OpenAlex/ScienceDirect don't surface. Use it when ours is
                        # missing — the ranker needs abstract tokens to score well.
                        if (not paper.abstract or len(paper.abstract) < 50) and item.get('abstract'):
                            cleaned = re.sub(r'<[^>]+>', ' ', item['abstract'])
                            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                            if len(cleaned) >= 50:
                                paper.abstract = cleaned

                except Exception as e:
                    logger.debug(f"Crossref enrichment failed for {paper.doi}: {e}")
        
        await asyncio.gather(
            *[enrich_single(p) for p in papers],
            return_exceptions=True
        )


class UnpaywallEnricher(PaperEnricher):
    """Enrich papers with Open Access information"""
    
    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig, email: str):
        self.session = session
        self.config = config
        self.email = email
    
    async def enrich(self, papers: List[DiscoveredPaper]) -> None:
        """Enrich papers with Unpaywall OA data"""
        if not papers or not self.email:
            return
        
        sem = asyncio.Semaphore(self.config.max_concurrent_enrichments)
        
        async def enrich_single(paper: DiscoveredPaper):
            if not paper.doi:
                return
                
            async with sem:
                try:
                    url = f"https://api.unpaywall.org/v2/{paper.doi}"
                    params = {'email': self.email}
                    
                    async with self.session.get(url, params=params) as resp:
                        if resp.status != 200:
                            return
                        
                        data = await resp.json()
                        
                        if data.get('is_oa'):
                            paper.is_open_access = True
                        
                        best_location = data.get('best_oa_location', {})
                        if best_location:
                            candidate_pdf = best_location.get('url_for_pdf')
                            if candidate_pdf:
                                try:
                                    host = urlparse(candidate_pdf).netloc.lower()
                                except Exception:
                                    host = ''
                                if host.endswith('nature.com'):
                                    candidate_pdf = None
                            if candidate_pdf:
                                paper.pdf_url = candidate_pdf
                            candidate_landing = best_location.get('url')
                            if candidate_landing:
                                try:
                                    host = urlparse(candidate_landing).netloc.lower()
                                except Exception:
                                    host = ''
                                if host.endswith('nature.com') and not candidate_pdf:
                                    candidate_landing = None
                            if candidate_landing:
                                paper.open_access_url = candidate_landing
                                
                except Exception as e:
                    logger.debug(f"Unpaywall enrichment failed for {paper.doi}: {e}")

        await asyncio.gather(
            *[enrich_single(p) for p in papers],
            return_exceptions=True
        )


class CacheAbstractEnricher(PaperEnricher):
    """Persistent-cache-backed abstract enricher.

    Reads from the `paper_abstracts` table for DOIs with empty abstracts, and
    fetches missing ones from free APIs (Elsevier / CORE / Semantic Scholar)
    in parallel. Results are written back to the cache so subsequent searches
    never repeat the fetch. Unavailable DOIs are marked so we don't retry.

    Runs early in the fallback phase because a cache hit is O(1) and
    eliminates the need for slower scrapes.
    """

    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig):
        self.session = session
        self.config = config

    async def enrich(self, papers: List[DiscoveredPaper]) -> None:
        from app.database import SessionLocal
        from app.services.paper_discovery.abstract_cache import fetch_missing

        db = SessionLocal()
        try:
            await fetch_missing(self.session, db, papers)
        except Exception as e:
            logger.warning("CacheAbstractEnricher failed: %s", e)
        finally:
            db.close()


class LandingAbstractEnricher(PaperEnricher):
    """Scrape publisher landing pages for abstracts when source metadata is empty.

    Springer (DOI prefix 10.1007/) renders the full abstract inside
    `<section data-title="Abstract">` — much richer than the truncated meta
    description. Other publishers either provide abstracts via Crossref/OpenAlex
    or actively block scraping (Elsevier/ScienceDirect).

    Cheap (~1s per fetch), high success rate for Springer, no API quota.
    """

    MIN_ABSTRACT_LEN = 50
    MAX_PARALLEL = 6
    MAX_FETCHES = 15
    PER_FETCH_TIMEOUT = 5.0

    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig):
        self.session = session
        self.config = config

    async def enrich(self, papers: List[DiscoveredPaper]) -> None:
        candidates = [
            p for p in papers
            if (not p.abstract or len(p.abstract) < self.MIN_ABSTRACT_LEN)
            and p.doi
            and self._landing_url(p.doi) is not None
        ][:self.MAX_FETCHES]
        if not candidates:
            return

        logger.info(
            "LandingAbstractEnricher: scraping %d publisher landing pages",
            len(candidates),
        )
        sem = asyncio.Semaphore(self.MAX_PARALLEL)
        successes = 0

        async def fetch_one(paper: DiscoveredPaper) -> bool:
            async with sem:
                url = self._landing_url(paper.doi)
                if not url:
                    return False
                try:
                    timeout = aiohttp.ClientTimeout(total=self.PER_FETCH_TIMEOUT)
                    headers = {"User-Agent": "Mozilla/5.0 (compatible; ScholarHub/1.0)"}
                    async with self.session.get(url, timeout=timeout, headers=headers, allow_redirects=True) as resp:
                        if resp.status != 200:
                            return False
                        text = await resp.text(errors="ignore")
                    abstract = self._parse_springer_abstract(text)
                    if abstract and len(abstract) >= self.MIN_ABSTRACT_LEN:
                        paper.abstract = abstract
                        return True
                except Exception as e:
                    logger.debug(
                        "LandingAbstractEnricher failed for %s: %s",
                        paper.doi or (paper.title or "")[:60],
                        e,
                    )
                return False

        results = await asyncio.gather(*[fetch_one(p) for p in candidates], return_exceptions=True)
        successes = sum(1 for r in results if r is True)
        logger.info(
            "LandingAbstractEnricher: extracted abstract for %d/%d papers",
            successes, len(candidates),
        )

    @staticmethod
    def _landing_url(doi: Optional[str]) -> Optional[str]:
        if not doi:
            return None
        clean = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "")
        if clean.startswith("10.1007/"):
            # Springer: chapters use 978- prefix in the suffix, articles don't
            suffix = clean[len("10.1007/"):]
            kind = "chapter" if "978-" in suffix.split("/")[0] else "article"
            return f"https://link.springer.com/{kind}/{clean}"
        return None

    @staticmethod
    def _parse_springer_abstract(html_text: str) -> str:
        if not html_text:
            return ""
        match = re.search(
            r'<section[^>]*data-title=[\'"]Abstract[\'"][^>]*>(.*?)</section>',
            html_text,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            return ""
        body = re.sub(r'<[^>]+>', ' ', match.group(1))
        # Decode minimal HTML entities; full unescape isn't critical
        body = body.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#x27;', "'")
        body = re.sub(r'\s+', ' ', body).strip()
        # Strip a leading "Abstract" heading word if present
        body = re.sub(r'^Abstract[\s:.-]*', '', body, flags=re.IGNORECASE).strip()
        return body[:1500]


class PdfAbstractEnricher(PaperEnricher):
    """Populate missing abstracts from the first page of an OA PDF.

    Publishers (Springer, Elsevier, etc.) often block abstracts in Crossref,
    OpenAlex, and Semantic Scholar metadata, but the abstract is typically
    printed on page 1 of the open-access PDF. When a paper has an accessible
    PDF URL and an empty/short abstract, this enricher fetches the first page
    and extracts the abstract text so the ranker has tokens to work with.

    Runs last so Unpaywall has already populated pdf_url/open_access_url.
    Bounded parallelism and per-fetch timeout cap the worst-case latency.
    """

    MIN_ABSTRACT_LEN = 50
    MAX_PARALLEL = 6
    MAX_FETCHES = 12
    PER_FETCH_TIMEOUT = 5.0

    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig):
        self.session = session
        self.config = config

    async def enrich(self, papers: List[DiscoveredPaper]) -> None:
        candidates = [
            p for p in papers
            if (not p.abstract or len(p.abstract) < self.MIN_ABSTRACT_LEN)
            and (p.pdf_url or p.open_access_url)
        ]
        if not candidates:
            return

        candidates = candidates[:self.MAX_FETCHES]
        logger.info(
            "PdfAbstractEnricher: fetching %d OA PDFs for missing abstracts",
            len(candidates),
        )

        sem = asyncio.Semaphore(self.MAX_PARALLEL)
        successes = 0
        failures = 0

        async def fetch_one(paper: DiscoveredPaper) -> bool:
            async with sem:
                url = paper.pdf_url or paper.open_access_url
                if not url:
                    return False
                try:
                    timeout = aiohttp.ClientTimeout(total=self.PER_FETCH_TIMEOUT)
                    headers = {"User-Agent": "Mozilla/5.0 (compatible; ScholarHub/1.0)"}
                    async with self.session.get(url, timeout=timeout, headers=headers) as resp:
                        if resp.status != 200:
                            return False
                        content_type = resp.headers.get("content-type", "").lower()
                        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                            return False
                        data = await resp.read()
                    extracted = await asyncio.to_thread(self._extract_first_page, data)
                    if not extracted:
                        return False
                    abstract = self._parse_abstract(extracted)
                    if abstract and len(abstract) >= self.MIN_ABSTRACT_LEN:
                        paper.abstract = abstract
                        return True
                except Exception as e:
                    logger.debug(
                        "PdfAbstractEnricher failed for %s: %s",
                        paper.doi or (paper.title or "")[:60],
                        e,
                    )
                return False

        results = await asyncio.gather(*[fetch_one(p) for p in candidates], return_exceptions=True)
        for r in results:
            if r is True:
                successes += 1
            else:
                failures += 1
        logger.info(
            "PdfAbstractEnricher: extracted abstract for %d/%d papers (%d failed)",
            successes, len(candidates), failures,
        )

    @staticmethod
    def _extract_first_page(pdf_bytes: bytes) -> str:
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            if not reader.pages:
                return ""
            return reader.pages[0].extract_text() or ""
        except Exception:
            return ""

    @staticmethod
    def _parse_abstract(page_text: str) -> str:
        """Locate an Abstract section and return the following paragraph."""
        if not page_text:
            return ""
        match = re.search(r'(?i)\babstract\b[\s:.\-]*\n?', page_text)
        if match:
            tail = page_text[match.end():match.end() + 2500]
            end_match = re.search(
                r'(?i)\n\s*(?:1\s+Introduction|I\.?\s+Introduction|Introduction\b|Keywords|Index Terms|Key words)',
                tail,
            )
            body = tail[:end_match.start()] if end_match else tail
            body = re.sub(r'\s+', ' ', body).strip()
            if len(body) >= PdfAbstractEnricher.MIN_ABSTRACT_LEN:
                return body[:1200]
        # Fallback: use a slice past the title/author block
        lines = [l.strip() for l in page_text.split('\n') if l.strip()]
        if len(lines) > 4:
            joined = ' '.join(lines[4:24])
            joined = re.sub(r'\s+', ' ', joined).strip()
            return joined[:1200]
        return ""
