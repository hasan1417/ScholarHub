"""Source-specific searchers for paper discovery."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlencode, urlparse, urljoin

import aiohttp
from bs4 import BeautifulSoup

from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.interfaces import PaperSearcher
from app.services.paper_discovery.models import DiscoveredPaper, PaperSource
from app.services.paper_discovery.query_builder import (
    build_arxiv_query,
    build_pubmed_query,
    build_europe_pmc_query,
)


logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when an API returns a rate limit response (429)."""
    pass


class SearcherBase(PaperSearcher):
    """Base class storing shared dependencies for searchers."""

    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig):
        self.session = session
        self.config = config


class ArxivSearcher(SearcherBase):
    """ArXiv paper searcher"""
    
    def get_source_name(self) -> str:
        return PaperSource.ARXIV.value
    
    async def search(self, query: str, max_results: int) -> List[DiscoveredPaper]:
        try:
            # Use optimized query builder for arXiv syntax
            optimized_query = build_arxiv_query(query)
            params = {
                'search_query': optimized_query,
                'start': 0,
                'max_results': max_results,
                'sortBy': 'relevance',
                'sortOrder': 'descending'
            }

            url = f"http://export.arxiv.org/api/query?{urlencode(params)}"
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"ArXiv API error: {response.status}")
                    return []
                
                content = await response.text()
                return self._parse_response(content)
                
        except Exception as e:
            logger.error(f"Error searching ArXiv: {e}")
            return []
    
    def _parse_response(self, xml_content: str) -> List[DiscoveredPaper]:
        """Parse ArXiv XML response"""
        papers = []
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_content)
            namespace = {'atom': 'http://www.w3.org/2005/Atom'}
            
            for entry in root.findall('atom:entry', namespace):
                title_elem = entry.find('atom:title', namespace)
                title_text = title_elem.text if title_elem is not None and title_elem.text is not None else ""
                title = title_text.strip() or "Unknown"
                
                authors = []
                for author in entry.findall('atom:author', namespace):
                    name = author.find('atom:name', namespace)
                    if name is not None and name.text is not None:
                        authors.append(name.text.strip())
                
                summary_elem = entry.find('atom:summary', namespace)
                summary_text = summary_elem.text if summary_elem is not None and summary_elem.text is not None else ""
                abstract = summary_text.strip()
                
                published_elem = entry.find('atom:published', namespace)
                year = None
                if published_elem is not None and published_elem.text:
                    try:
                        year = int(published_elem.text.strip()[:4])
                    except (ValueError, TypeError):
                        pass
                
                url = None
                for link in entry.findall('atom:link', namespace):
                    href = link.get('href', '')
                    if 'arxiv.org/abs/' in href:
                        url = href
                        break
                
                pdf_url = None
                if url and 'arxiv.org/abs/' in url:
                    pdf_url = url.replace('/abs/', '/pdf/') + '.pdf'

                # Extract primary category as venue (e.g., "arXiv:cs.LG")
                primary_category = None
                category_elem = entry.find('{http://arxiv.org/schemas/atom}primary_category')
                if category_elem is not None:
                    term = category_elem.get('term')
                    if term:
                        primary_category = f"arXiv:{term}"

                papers.append(DiscoveredPaper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    doi=None,
                    url=url,
                    source=self.get_source_name(),
                    is_open_access=True,
                    pdf_url=pdf_url,
                    journal=primary_category,
                ))
        except Exception as e:
            logger.error(f"Error parsing ArXiv response: {e}")
        
        return papers


class SemanticScholarSearcher(SearcherBase):
    """Semantic Scholar paper searcher"""
    
    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig, api_key: Optional[str] = None):
        super().__init__(session, config)
        self.api_key = api_key
    
    def get_source_name(self) -> str:
        return PaperSource.SEMANTIC_SCHOLAR.value
    
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        open_access_only: bool = False,
    ) -> List[DiscoveredPaper]:
        try:
            headers = {'User-Agent': 'ScholarHub/1.0'}
            if self.api_key:
                headers['x-api-key'] = self.api_key
            
            params = {
                "query": query,
                "limit": max_results,
                "fields": "title,year,authors,venue,url,externalIds,abstract,citationCount,isOpenAccess,openAccessPdf"
            }
            if year_from is not None or year_to is not None:
                start = year_from if year_from is not None else 1900
                end = year_to if year_to is not None else datetime.now(timezone.utc).year
                if start > end:
                    start, end = end, start
                params["year"] = f"{start}-{end}"
            if open_access_only:
                # Semantic Scholar supports this as a query parameter.
                params["openAccessPdf"] = "true"
            
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 429:
                    logger.warning("Semantic Scholar rate limited")
                    raise RateLimitError("Semantic Scholar API rate limited")
                elif response.status != 200:
                    logger.error(f"Semantic Scholar error: {response.status}")
                    return []

                data = await response.json()
                return await self._parse_response(data)

        except RateLimitError:
            raise  # Re-raise rate limit errors to be handled by orchestrator
        except Exception as e:
            logger.error(f"Error searching Semantic Scholar: {e}")
            return []
    
    async def _parse_response(self, data: Dict[str, Any]) -> List[DiscoveredPaper]:
        """Parse Semantic Scholar JSON response"""
        papers: List[DiscoveredPaper] = []
        for item in data.get('data', []):
            authors = [
                author['name']
                for author in item.get('authors', [])
                if author.get('name')
            ]

            external_ids = item.get('externalIds') or {}
            doi = external_ids.get('DOI')
            arxiv_id = external_ids.get('ArXiv') or external_ids.get('ARXIV')

            # Fast PDF extraction from metadata only (no HTTP requests)
            pdf_url = None
            oapdf = item.get('openAccessPdf') or {}
            if isinstance(oapdf, dict):
                pdf_url = (oapdf.get('url') or '').strip() or None

            # Try to derive arXiv PDF URL (no HTTP request)
            if not pdf_url:
                pdf_url = self._derive_arxiv_pdf(doi=doi, url=item.get('url'), arxiv_id=arxiv_id)

            papers.append(DiscoveredPaper(
                title=item.get('title', ''),
                authors=authors,
                abstract=item.get('abstract', ''),
                year=item.get('year'),
                doi=doi,
                url=item.get('url'),
                source=self.get_source_name(),
                citations_count=item.get('citationCount', 0),
                journal=item.get('venue', ''),
                is_open_access=bool(item.get('isOpenAccess') or pdf_url),
                pdf_url=pdf_url
            ))

        return papers

    async def _find_pdf_via_semantic_page(self, item: Dict[str, Any]) -> Optional[str]:
        semantic_url = item.get('url') or ''
        if 'semanticscholar.org' not in semantic_url:
            return None

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        timeout = aiohttp.ClientTimeout(total=min(12.0, max(6.0, self.config.search_timeout)))
        try:
            async with self.session.get(semantic_url, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.debug("Semantic Scholar landing page returned %s", resp.status)
                    return None
                html = await resp.text()
        except Exception as exc:
            logger.debug("Failed to fetch Semantic Scholar page: %s", exc)
            return None

        candidates = self._extract_pdf_candidates(html, semantic_url)
        if not candidates:
            return None

        for candidate in candidates:
            verified = await self._verify_pdf_candidate(candidate)
            if verified:
                return verified
        return None

    def _extract_pdf_candidates(self, html: str, base_url: str) -> List[str]:
        candidates: List[str] = []
        seen: Set[str] = set()
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return candidates

        def add_candidate(href: Optional[str]) -> None:
            if not href:
                return
            full = urljoin(base_url, href)
            if full and full not in seen:
                seen.add(full)
                candidates.append(full)

        # Meta tags sometimes expose the PDF directly
        for meta in soup.find_all('meta', attrs={'name': 'citation_pdf_url'}):
            add_candidate(meta.get('content'))

        # Anchors/buttons with PDF intent
        keywords = ('pdf', 'download', 'full text')
        publisher_words = ('publisher', 'view paper', 'view publication')

        for tag in soup.find_all(['a', 'button'], href=True):
            href = tag.get('href')
            text = (tag.get_text() or '').strip().lower()
            selector = (tag.get('data-selenium-selector') or '').lower()

            if any(word in text for word in keywords) or selector in {'paper-link', 'pdf-link'} or (href and 'pdf' in href.lower()):
                add_candidate(href)
            elif any(word in text for word in publisher_words):
                add_candidate(href)

        # Buttons/divs with data-href attributes
        for tag in soup.find_all(attrs={'data-href': True}):
            data_href = tag.get('data-href')
            text = (tag.get_text() or '').strip().lower()
            if data_href and (('pdf' in (data_href.lower())) or any(word in text for word in keywords)):
                add_candidate(data_href)

        return candidates

    async def _verify_pdf_candidate(self, url: str, depth: int = 0, visited: Optional[Set[str]] = None) -> Optional[str]:
        if visited is None:
            visited = set()
        if url in visited or depth > 2:
            return None
        visited.add(url)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,application/octet-stream;q=0.9,*/*;q=0.8',
        }
        timeout = aiohttp.ClientTimeout(total=max(5.0, self.config.pdf_check_timeout))

        try:
            async with self.session.head(url, allow_redirects=True, headers=headers, timeout=timeout) as resp:
                final_url = str(resp.url)
                content_type = (resp.headers.get('content-type') or '').lower()
                if 'pdf' in content_type or final_url.lower().endswith('.pdf'):
                    return final_url
        except Exception:
            pass

        try:
            async with self.session.get(url, allow_redirects=True, headers=headers, timeout=timeout) as resp:
                final_url = str(resp.url)
                content_type = (resp.headers.get('content-type') or '').lower()
                if 'pdf' in content_type or final_url.lower().endswith('.pdf'):
                    return final_url

                if resp.status == 200 and 'html' in content_type:
                    html = await resp.text()
                    nested = self._extract_pdf_candidates(html, final_url)
                    for candidate in nested:
                        verified = await self._verify_pdf_candidate(candidate, depth + 1, visited)
                        if verified:
                            return verified
        except Exception:
            pass

        return None

    @staticmethod
    def _derive_arxiv_pdf(doi: Optional[str], url: Optional[str], arxiv_id: Optional[str]) -> Optional[str]:
        """Attempt to synthesize an arXiv PDF when Semantic Scholar omits the link."""

        def normalize_arxiv(identifier: Optional[str]) -> Optional[str]:
            if not identifier:
                return None
            identifier = identifier.strip()
            if not identifier:
                return None
            identifier = identifier.replace('arXiv:', '').replace('ARXIV:', '')
            return identifier or None

        candidate_id = normalize_arxiv(arxiv_id)

        if not candidate_id and doi:
            doi_lower = doi.lower().strip()
            if doi_lower.startswith('10.48550/arxiv.'):
                candidate_id = doi.split('arXiv.')[-1]
            elif doi_lower.startswith('10.48550/arxiv:'):
                candidate_id = doi.split('arXiv:')[-1]
            elif doi_lower.startswith('arxiv:'):
                candidate_id = doi.split(':', 1)[-1]

        if not candidate_id and url:
            try:
                parsed = urlparse(url)
                path = parsed.path or ''
                if 'arxiv.org' in parsed.netloc and '/abs/' in path:
                    candidate_id = path.split('/abs/')[-1]
            except Exception:
                candidate_id = None

        candidate_id = normalize_arxiv(candidate_id)
        if not candidate_id:
            return None

        # arXiv PDFs accept identifiers with or without version suffix
        return f"https://arxiv.org/pdf/{candidate_id}.pdf"


class CrossrefSearcher(SearcherBase):
    """Crossref searcher to fetch papers by query."""

    def get_source_name(self) -> str:
        return PaperSource.CROSSREF.value

    async def search(self, query: str, max_results: int) -> List[DiscoveredPaper]:
        logger.info(f"CrossrefSearcher searching for: '{query}' (max_results: {max_results})")
        try:
            if not query or query.strip() == '':
                logger.warning("CrossrefSearcher received empty query")
                return []

            # Build polite headers with contact email per Crossref etiquette
            try:
                from app.core.config import settings as _settings  # local import to avoid global dependency
                contact_email = getattr(_settings, 'UNPAYWALL_EMAIL', None) or os.getenv('CROSSREF_MAILTO') or 'contact@example.com'
            except Exception:  # pragma: no cover
                contact_email = os.getenv('CROSSREF_MAILTO') or 'contact@example.com'

            # Clamp rows to a reasonable number to reduce payload and avoid throttling
            rows = max(5, min(int(max_results or 20), 25))

            base_params = {
                'query': query.strip()[:400],  # avoid overly long queries
                'rows': rows,
                'select': ','.join([
                    'DOI', 'title', 'author', 'issued', 'URL', 'abstract',
                    'container-title', 'is-referenced-by-count'
                ]),
                'mailto': contact_email,
            }
            headers = {'User-Agent': f'ScholarHub/1.0 (mailto:{contact_email})'}

            # Retry with backoff on transient failures/timeouts
            attempts = 3
            backoff_seconds = [0.0, 0.75, 1.5]
            timeout = aiohttp.ClientTimeout(total=60)

            for attempt in range(attempts):
                if attempt:
                    await asyncio.sleep(backoff_seconds[min(attempt, len(backoff_seconds)-1)])
                url = f"https://api.crossref.org/works?{urlencode(base_params)}"
                try:
                    async with self.session.get(url, headers=headers, timeout=timeout) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            items_count = len(((data or {}).get('message') or {}).get('items', []))
                            logger.info("Crossref API returned %s items (attempt %s)", items_count, attempt+1)
                            return await self._parse_response(data)
                        # Retry on throttling or server errors
                        if resp.status in (429, 500, 502, 503, 504):
                            text = await resp.text()
                            logger.warning("Crossref transient error %s on attempt %s: %s", resp.status, attempt+1, text[:200])
                            continue
                        # For other statuses, don't retry
                        text = await resp.text()
                        logger.error("Crossref API error: %s - %s", resp.status, text[:200])
                        return []
                except asyncio.TimeoutError:
                    logger.warning("Crossref request timed out on attempt %s", attempt+1)
                    continue
                except Exception as exc:
                    logger.warning("Crossref request failed on attempt %s: %s", attempt+1, exc)
                    continue

            logger.error("Crossref failed after %s attempts", attempts)
            return []
        except Exception as exc:
            logger.error("Error searching Crossref: %s", exc)
            return []

    async def _parse_response(self, data: Dict[str, Any]) -> List[DiscoveredPaper]:
        items = ((data or {}).get('message') or {}).get('items', [])
        papers: List[DiscoveredPaper] = []

        # First pass: parse metadata without PDF lookup (fast)
        for it in items:
            try:
                title_list = it.get('title') or []
                title = (title_list[0] if title_list else '') or ''
                authors = []
                for a in it.get('author') or []:
                    name = ' '.join(filter(None, [a.get('given'), a.get('family')])).strip()
                    if name:
                        authors.append(name)
                doi = it.get('DOI') or None
                url = it.get('URL') or None
                year = None
                issued = it.get('issued', {})
                try:
                    parts = (issued.get('date-parts') or [[]])[0]
                    if parts:
                        year = int(parts[0])
                except Exception:
                    year = None
                abstract = it.get('abstract') or ''

                # Extract journal/venue with fallbacks
                journal_list = it.get('container-title') or []
                journal = journal_list[0] if journal_list else None

                # Fallback: conference/event name for proceedings
                if not journal:
                    event = it.get('event') or {}
                    if isinstance(event, dict):
                        journal = event.get('name')

                # Fallback: publisher for books/reports
                if not journal:
                    publisher = it.get('publisher')
                    doc_type = it.get('type', '')
                    if publisher and doc_type in ('book', 'report', 'monograph', 'posted-content'):
                        journal = publisher

                citations = it.get('is-referenced-by-count')

                # Quick PDF check from metadata only (no HTTP requests)
                pdf_url = self._extract_pdf_from_metadata(it)
                is_open_access = bool(pdf_url)

                papers.append(DiscoveredPaper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    doi=doi,
                    url=url,
                    source=self.get_source_name(),
                    citations_count=citations if isinstance(citations, int) else None,
                    journal=journal,
                    is_open_access=is_open_access,
                    open_access_url=pdf_url if pdf_url else None,
                    pdf_url=pdf_url,
                ))
            except Exception:
                logger.debug("Failed parsing Crossref item", exc_info=True)
                continue
        return papers

    def _extract_pdf_from_metadata(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract PDF URL from Crossref metadata without making HTTP requests."""
        # Check link array for PDF content-type
        for link_info in item.get('link') or []:
            if not isinstance(link_info, dict):
                continue
            content_type = (link_info.get('content-type') or '').lower()
            candidate = (link_info.get('URL') or '').strip()
            if candidate and 'pdf' in content_type:
                return candidate
            # Also check if URL itself looks like a PDF
            if candidate and candidate.lower().endswith('.pdf'):
                return candidate
        return None

    async def _extract_pdf_from_links(self, item: Dict[str, Any]) -> Optional[str]:
        for link_info in item.get('link') or []:
            if not isinstance(link_info, dict):
                continue
            content_type = (link_info.get('content-type') or '').lower()
            candidate = (link_info.get('URL') or '').strip()
            if candidate and 'pdf' in content_type:
                verified = await self._verify_pdf_candidate(candidate)
                if verified:
                    return verified
        return None

    async def _locate_crossref_pdf(self, item: Dict[str, Any]) -> Optional[str]:
        direct = await self._extract_pdf_from_links(item)
        if direct:
            return direct

        doi = (item.get('DOI') or '').strip()
        url = (item.get('URL') or '').strip()

        candidate_urls: List[str] = []
        if doi:
            candidate_urls.append(f"https://doi.org/{doi}")
        if url and url not in candidate_urls:
            candidate_urls.append(url)

        for candidate in candidate_urls:
            verified = await self._verify_pdf_candidate(candidate)
            if verified:
                return verified
        return None

    async def _verify_pdf_candidate(self, url: str, depth: int = 0, visited: Optional[Set[str]] = None) -> Optional[str]:
        if visited is None:
            visited = set()
        if depth > 2 or url in visited:
            return None
        visited.add(url)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,application/octet-stream;q=0.9,*/*;q=0.8',
        }
        timeout = aiohttp.ClientTimeout(total=max(5.0, self.config.pdf_check_timeout))

        try:
            async with self.session.head(url, allow_redirects=True, headers=headers, timeout=timeout) as resp:
                final_url = str(resp.url)
                content_type = (resp.headers.get('content-type') or '').lower()
                if 'pdf' in content_type or final_url.lower().endswith('.pdf'):
                    return final_url
        except Exception:
            pass

        try:
            async with self.session.get(url, allow_redirects=True, headers=headers, timeout=timeout) as resp:
                final_url = str(resp.url)
                content_type = (resp.headers.get('content-type') or '').lower()
                if 'pdf' in content_type or final_url.lower().endswith('.pdf'):
                    return final_url

                if resp.status == 200 and 'html' in content_type:
                    html = await resp.text()
                    nested = self._extract_pdf_candidates(html, final_url)
                    for candidate in nested:
                        verified = await self._verify_pdf_candidate(candidate, depth + 1, visited)
                        if verified:
                            return verified
        except Exception:
            pass

        return None

    def _extract_pdf_candidates(self, html: str, base_url: str) -> List[str]:
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return []

        candidates: List[str] = []
        seen: Set[str] = set()
        keywords = ('pdf', 'download', 'full text')

        def add_candidate(href: Optional[str]):
            if not href:
                return
            full = urljoin(base_url, href)
            if full and full not in seen:
                seen.add(full)
                candidates.append(full)

        for meta in soup.find_all('meta', attrs={'name': 'citation_pdf_url'}):
            add_candidate(meta.get('content'))

        for tag in soup.find_all(['a', 'button'], href=True):
            href = tag.get('href')
            text = (tag.get_text() or '').strip().lower()
            if any(word in text for word in keywords) or (href and 'pdf' in href.lower()):
                add_candidate(href)

        for tag in soup.find_all(attrs={'data-href': True}):
            href = tag.get('data-href')
            text = (tag.get_text() or '').strip().lower()
            if any(word in text for word in keywords) or (href and 'pdf' in href.lower()):
                add_candidate(href)

        return candidates


class PubMedSearcher(SearcherBase):
    """PubMed searcher leveraging NCBI E-utilities."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig, email: Optional[str] = None):
        super().__init__(session, config)
        self.email = email

    def get_source_name(self) -> str:
        return PaperSource.PUBMED.value

    async def search(self, query: str, max_results: int) -> List[DiscoveredPaper]:
        logger.info(f"PubMedSearcher searching for: '{query}' (max_results: {max_results})")
        try:
            if not query or not query.strip():
                logger.warning("PubMedSearcher received empty query")
                return []

            ids = await self._esearch(query, max_results)
            if not ids:
                return []

            summaries = await self._esummary(ids)
            if not summaries:
                return []

            abstracts = await self._efetch_abstracts(ids)

            papers: List[DiscoveredPaper] = []
            for pmid in ids:
                item = summaries.get(pmid)
                if not item:
                    continue

                title = (item.get('title') or '').strip()
                if not title:
                    continue

                authors: List[str] = []
                for author_entry in item.get('authors') or []:
                    if not isinstance(author_entry, dict):
                        continue
                    raw_name = author_entry.get('name')
                    if not isinstance(raw_name, str):
                        continue
                    name = raw_name.strip()
                    if name:
                        authors.append(name)

                year = self._extract_year(item)
                doi = self._extract_doi(item)
                journal = item.get('fulljournalname')
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

                pmc_id = self._extract_pmc_id(item)
                is_open_access = pmc_id is not None
                open_access_url = None
                pdf_url = None
                if pmc_id:
                    open_access_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
                    pdf_url = f"{open_access_url}pdf"

                papers.append(
                    DiscoveredPaper(
                        title=title,
                        authors=authors,
                        abstract=abstracts.get(pmid, ''),
                        year=year,
                        doi=doi,
                        url=url,
                        source=self.get_source_name(),
                        journal=journal,
                        is_open_access=is_open_access,
                        open_access_url=open_access_url,
                        pdf_url=pdf_url,
                    )
                )

            return papers
        except Exception as exc:
            logger.error("Error searching PubMed: %s", exc)
            return []

    async def _esearch(self, query: str, max_results: int) -> List[str]:
        # Use optimized query builder for PubMed syntax
        optimized_query = build_pubmed_query(query)
        params = {
            'db': 'pubmed',
            'term': optimized_query[:400],
            'retmode': 'json',
            'retmax': max(1, min(int(max_results or 20), 25)),
            'tool': 'ScholarHub',
        }
        if self.email:
            params['email'] = self.email

        timeout = aiohttp.ClientTimeout(total=30)
        async with self.session.get(
            f"{self.BASE_URL}esearch.fcgi",
            params=params,
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                logger.warning("PubMed esearch returned status %s", resp.status)
                return []
            data = await resp.json(content_type=None)
            id_list = ((data or {}).get('esearchresult') or {}).get('idlist') or []
            return [pmid for pmid in id_list if pmid]

    async def _esummary(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        params = {
            'db': 'pubmed',
            'retmode': 'json',
            'id': ','.join(ids),
            'tool': 'ScholarHub',
        }
        if self.email:
            params['email'] = self.email

        timeout = aiohttp.ClientTimeout(total=30)
        async with self.session.get(
            f"{self.BASE_URL}esummary.fcgi",
            params=params,
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                logger.warning("PubMed esummary returned status %s", resp.status)
                return {}
            data = await resp.json(content_type=None)
            result = (data or {}).get('result') or {}
            summaries: Dict[str, Dict[str, Any]] = {}
            for pmid in ids:
                item = result.get(pmid)
                if isinstance(item, dict):
                    summaries[pmid] = item
            return summaries

    async def _efetch_abstracts(self, ids: List[str]) -> Dict[str, str]:
        params = {
            'db': 'pubmed',
            'retmode': 'xml',
            'rettype': 'abstract',
            'id': ','.join(ids),
            'tool': 'ScholarHub',
        }
        if self.email:
            params['email'] = self.email

        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with self.session.get(
                f"{self.BASE_URL}efetch.fcgi",
                params=params,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    logger.warning("PubMed efetch returned status %s", resp.status)
                    return {}
                xml_text = await resp.text()
        except Exception as exc:
            logger.warning("PubMed efetch failed: %s", exc)
            return {}

        abstracts: Dict[str, str] = {}
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("PubMed efetch XML parse error: %s", exc)
            return {}

        for article in root.findall('.//PubmedArticle'):
            pmid_el = article.find('.//MedlineCitation/PMID')
            if pmid_el is None or pmid_el.text is None:
                continue
            pmid = pmid_el.text.strip()
            abstract_chunks = []
            for abstract_el in article.findall('.//Abstract/AbstractText'):
                text = ''.join(abstract_el.itertext()).strip()
                if not text:
                    continue
                label = abstract_el.get('Label')
                if label:
                    text = f"{label}: {text}"
                abstract_chunks.append(text)
            if abstract_chunks:
                abstracts[pmid] = '\n'.join(abstract_chunks)
        return abstracts

    @staticmethod
    def _extract_year(item: Dict[str, Any]) -> Optional[int]:
        candidates = [item.get('sortpubdate'), item.get('pubdate')]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                year = int(str(candidate)[:4])
                current_year = datetime.utcnow().year
                if 1600 <= year <= current_year + 1:
                    return year
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_doi(item: Dict[str, Any]) -> Optional[str]:
        for entry in item.get('articleids') or []:
            if not isinstance(entry, dict):
                continue
            if entry.get('idtype') == 'doi' and entry.get('value'):
                return entry['value']
        return None

    @staticmethod
    def _extract_pmc_id(item: Dict[str, Any]) -> Optional[str]:
        for entry in item.get('articleids') or []:
            if not isinstance(entry, dict):
                continue
            idtype = (entry.get('idtype') or '').lower()
            value = (entry.get('value') or '').strip()
            if not value:
                continue
            if idtype == 'pmc':
                return value
            if idtype == 'pmcid':
                cleaned = value.replace('pmc-id:', '').replace(';', '').strip()
                if cleaned.upper().startswith('PMC'):
                    return cleaned.upper()
        return None


class ScienceDirectSearcher(SearcherBase):
    """ScienceDirect searcher using Elsevier APIs."""

    BASE_URL = "https://api.elsevier.com/content/search/sciencedirect"

    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig, api_key: Optional[str]):
        super().__init__(session, config)
        self.api_key = api_key

    def get_source_name(self) -> str:
        return PaperSource.SCIENCEDIRECT.value

    async def search(self, query: str, max_results: int) -> List[DiscoveredPaper]:
        logger.info(f"ScienceDirectSearcher searching for: '{query}' (max_results: {max_results})")

        if not self.api_key:
            logger.warning("ScienceDirectSearcher disabled: missing API key")
            return []
        if not query or not query.strip():
            logger.warning("ScienceDirectSearcher received empty query")
            return []

        params = {
            'query': query.strip()[:400],
            'count': max(1, min(int(max_results or 20), 25)),
            'start': 0,
            'httpAccept': 'application/json',
        }

        headers = {
            'X-ELS-APIKey': self.api_key,
            'Accept': 'application/json',
        }

        timeout = aiohttp.ClientTimeout(total=30)

        try:
            async with self.session.get(self.BASE_URL, params=params, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("ScienceDirect API status %s: %s", resp.status, text[:200])
                    return []
                data = await resp.json(content_type=None)
        except asyncio.TimeoutError:
            logger.warning("ScienceDirect request timed out")
            return []
        except Exception as exc:
            logger.error("ScienceDirect request failed: %s", exc)
            return []

        entries_raw = ((data or {}).get('search-results') or {}).get('entry') or []
        entries = entries_raw if isinstance(entries_raw, list) else [entries_raw]
        papers: List[DiscoveredPaper] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            title = (entry.get('dc:title') or '').strip()
            if not title:
                continue

            authors_data = (entry.get('authors') or {}).get('author') or []
            authors: List[str] = []
            for author in authors_data:
                if not isinstance(author, dict):
                    continue
                parts = [author.get('given-name'), author.get('surname')]
                name = ' '.join(part.strip() for part in parts if part and part.strip())
                if name:
                    authors.append(name)

            abstract = (entry.get('dc:description') or entry.get('prism:teaser') or '').strip()
            doi = (entry.get('prism:doi') or '').strip() or None
            year = self._extract_year(entry)
            journal = (entry.get('prism:publicationName') or '').strip() or None

            url = None
            for link in entry.get('link') or []:
                if not isinstance(link, dict):
                    continue
                if link.get('@ref') == 'scidir' and link.get('@href'):
                    url = link['@href']
                    break
            if not url:
                url = entry.get('prism:url')

            open_access_value = entry.get('openaccess')
            if isinstance(open_access_value, str):
                is_open_access = open_access_value.strip() in {'1', 'true', 'True'}
            elif isinstance(open_access_value, (int, float)):
                is_open_access = bool(open_access_value)
            elif isinstance(open_access_value, bool):
                is_open_access = open_access_value
            else:
                is_open_access = False
            pdf_url = None
            if is_open_access:
                for link in entry.get('link') or []:
                    if not isinstance(link, dict):
                        continue
                    if link.get('@ref') == 'sciencedirect' and link.get('@href'):
                        pdf_url = link['@href']
                        break

            papers.append(
                DiscoveredPaper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    doi=doi,
                    url=url,
                    source=self.get_source_name(),
                    journal=journal,
                    is_open_access=is_open_access,
                    pdf_url=pdf_url,
                )
            )

        return papers

    @staticmethod
    def _extract_year(entry: Dict[str, Any]) -> Optional[int]:
        candidates = [entry.get('prism:coverDate'), entry.get('prism:coverDisplayDate')]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                year = int(str(candidate)[:4])
                current_year = datetime.utcnow().year
                if 1600 <= year <= current_year + 1:
                    return year
            except Exception:
                continue
        return None


class OpenAlexSearcher(SearcherBase):
    """OpenAlex searcher for open scholarly metadata."""

    def get_source_name(self) -> str:
        return PaperSource.OPENALEX.value

    async def search(
        self,
        query: str,
        max_results: int,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        open_access_only: bool = False,
    ) -> List[DiscoveredPaper]:
        logger.info(f"OpenAlexSearcher searching for: '{query}' (max_results: {max_results})")
        try:
            if not query or query.strip() == '':
                logger.warning("OpenAlexSearcher received empty query")
                return []

            # Build query parameters
            params = {
                'search': query.strip()[:400],  # Search parameter works for OpenAlex
                'per-page': min(int(max_results or 20), 25),  # Limit results
                'select': 'id,display_name,authorships,publication_year,abstract_inverted_index,doi,primary_location,open_access,best_oa_location',
                # 'mailto': 'contact@example.com',  # Remove mailto to avoid issues
            }
            filters = []
            if year_from is not None:
                filters.append(f"from_publication_date:{year_from}-01-01")
            if year_to is not None:
                filters.append(f"to_publication_date:{year_to}-12-31")
            if open_access_only:
                filters.append("is_oa:true")
            if filters:
                params["filter"] = ",".join(filters)

            # OpenAlex API endpoint
            url = f"https://api.openalex.org/works?{urlencode(params)}"
            headers = {'User-Agent': 'ScholarHub/1.0 (mailto:contact@example.com)'}

            # Retry with backoff on failures
            attempts = 3
            backoff_seconds = [0.0, 1.0, 2.0]
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout for OpenAlex

            for attempt in range(attempts):
                if attempt:
                    await asyncio.sleep(backoff_seconds[min(attempt, len(backoff_seconds)-1)])
                try:
                    async with self.session.get(url, headers=headers, timeout=timeout) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            items = data.get('results', [])
                            logger.info("OpenAlex API returned %s items (attempt %s)", len(items), attempt+1)
                            return self._parse_response(items)
                        elif resp.status in (429, 500, 502, 503, 504):
                            text = await resp.text()
                            logger.warning("OpenAlex transient error %s on attempt %s: %s", resp.status, attempt+1, text[:200])
                            continue
                        else:
                            text = await resp.text()
                            logger.error("OpenAlex API error: %s - %s", resp.status, text[:200])
                            return []
                except asyncio.TimeoutError:
                    logger.warning("OpenAlex request timed out on attempt %s", attempt+1)
                    continue
                except Exception as exc:
                    logger.warning("OpenAlex request failed on attempt %s: %s", attempt+1, exc)
                    continue

            logger.error("OpenAlex failed after %s attempts", attempts)
            return []
        except Exception as exc:
            logger.error("Error searching OpenAlex: %s", exc)
            return []

    def _parse_response(self, items: List[Dict[str, Any]]) -> List[DiscoveredPaper]:
        papers: List[DiscoveredPaper] = []

        for item in items:
            try:
                # Extract title
                title = item.get('display_name', '').strip()
                if not title:
                    continue

                # Extract authors
                authors = []
                authorships = item.get('authorships', [])
                for authorship in authorships:
                    author_info = authorship.get('author', {})
                    display_name = author_info.get('display_name', '')
                    if display_name:
                        authors.append(display_name)

                # Extract year
                year = item.get('publication_year')

                # Extract DOI
                doi = item.get('doi')

                # Extract abstract
                abstract = ""
                abstract_index = item.get('abstract_inverted_index', {})
                if abstract_index:
                    # Reconstruct abstract from inverted index
                    words = [''] * max(abstract_index.keys()) if abstract_index else []
                    for word, positions in abstract_index.items():
                        for pos in positions:
                            if pos < len(words):
                                words[pos] = word
                    abstract = ' '.join(words).strip()

                # Extract URL / OA info
                url = None
                pdf_url = None
                primary_location = item.get('primary_location', {})
                if isinstance(primary_location, dict):
                    landing_page = primary_location.get('landing_page_url')
                    if landing_page:
                        url = landing_page
                    if primary_location.get('pdf_url'):
                        pdf_url = primary_location.get('pdf_url')

                best_oa_location = item.get('best_oa_location') or {}
                if best_oa_location and not pdf_url:
                    pdf_url = best_oa_location.get('url_for_pdf')
                    if not url:
                        url = best_oa_location.get('url') or url

                open_access = item.get('open_access', {})
                is_open_access = open_access.get('is_oa', False)
                open_access_url = None
                if is_open_access:
                    open_access_url = open_access.get('oa_url')
                    if not pdf_url:
                        pdf_url = open_access_url if open_access_url and open_access_url.lower().endswith('.pdf') else pdf_url

                if not open_access_url and pdf_url:
                    open_access_url = pdf_url

                # Some providers (e.g., nature.com) report a PDF URL that actually
                # serves HTML. Defer to downstream verification by clearing it now.
                if pdf_url:
                    try:
                        parsed_host = urlparse(pdf_url).netloc.lower()
                    except Exception:
                        parsed_host = ''
                    if parsed_host.endswith('nature.com'):
                        pdf_url = None
                        is_open_access = False
                        if open_access_url and open_access_url.lower().endswith('.pdf'):
                            open_access_url = url

                papers.append(DiscoveredPaper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    doi=doi,
                    url=url,
                    source=self.get_source_name(),
                    relevance_score=0.0,  # Will be set by ranker
                    citations_count=None,  # OpenAlex doesn't provide citation counts in basic search
                    journal=None,
                    keywords=[],
                    raw_data=item,
                    is_open_access=is_open_access,
                    open_access_url=open_access_url,
                    pdf_url=pdf_url,
                ))
            except Exception:
                continue

        return papers


class CoreSearcher(SearcherBase):
    """CORE (core.ac.uk) paper searcher - 200M+ open access papers."""

    def __init__(self, session: aiohttp.ClientSession, config: DiscoveryConfig, api_key: Optional[str] = None):
        super().__init__(session, config)
        self.api_key = api_key

    def get_source_name(self) -> str:
        return PaperSource.CORE.value

    async def search(self, query: str, max_results: int) -> List[DiscoveredPaper]:
        if not self.api_key:
            logger.warning("CORE API key not configured, skipping CORE search")
            return []

        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
            }

            # CORE API v3 search endpoint (trailing slash required to avoid redirect)
            url = "https://api.core.ac.uk/v3/search/works/"
            params = {
                'q': query,
                'limit': min(max_results, 100),  # CORE max is 100 per request
            }

            print(f"[CORE] Searching for '{query}' with limit {max_results}")
            logger.info(f"CORE: Searching for '{query}' with limit {max_results}")
            async with self.session.get(url, params=params, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=40)) as response:
                logger.info(f"CORE: Response status {response.status}")
                if response.status == 429:
                    logger.warning("CORE API rate limited")
                    raise RateLimitError("CORE API rate limited")
                elif response.status == 401:
                    logger.error("CORE API authentication failed - check API key")
                    return []
                elif response.status != 200:
                    text = await response.text()
                    logger.error(f"CORE API error: {response.status} - {text[:200]}")
                    return []

                data = await response.json()
                logger.info(f"CORE: Got {len(data.get('results', []))} results")
                return self._parse_response(data)

        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Error searching CORE: {e}")
            return []

    def _parse_response(self, data: Dict[str, Any]) -> List[DiscoveredPaper]:
        """Parse CORE API response."""
        papers = []
        results = data.get('results', [])

        for item in results:
            try:
                title = (item.get('title') or '').strip()
                if not title:
                    continue

                # Extract authors
                authors = []
                for author in item.get('authors', []):
                    if isinstance(author, dict):
                        name = author.get('name', '')
                    else:
                        name = str(author)
                    if name:
                        authors.append(name)

                abstract = (item.get('abstract') or '').strip()
                year = item.get('yearPublished')

                # Get DOI
                doi = item.get('doi')
                if doi and doi.startswith('http'):
                    # Extract DOI from URL
                    doi = doi.replace('https://doi.org/', '').replace('http://doi.org/', '')

                # Get URLs
                url = item.get('downloadUrl') or item.get('sourceFulltextUrls', [None])[0] if item.get('sourceFulltextUrls') else None
                if not url:
                    url = f"https://core.ac.uk/works/{item.get('id')}" if item.get('id') else None

                # PDF URL
                pdf_url = item.get('downloadUrl')
                if pdf_url and not pdf_url.lower().endswith('.pdf'):
                    pdf_url = None

                papers.append(DiscoveredPaper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    doi=doi,
                    url=url,
                    source=self.get_source_name(),
                    is_open_access=True,  # CORE focuses on open access
                    pdf_url=pdf_url,
                ))
            except Exception as e:
                logger.debug(f"Error parsing CORE result: {e}")
                continue

        return papers


class EuropePmcSearcher(SearcherBase):
    """Europe PMC paper searcher - biomedical and life sciences literature."""

    def get_source_name(self) -> str:
        return PaperSource.EUROPE_PMC.value

    async def search(self, query: str, max_results: int) -> List[DiscoveredPaper]:
        try:
            # Use optimized query builder for Europe PMC syntax
            optimized_query = build_europe_pmc_query(query)
            # Europe PMC REST API
            url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
            params = {
                'query': optimized_query,
                'format': 'json',
                'pageSize': min(max_results, 100),  # Max 100 per request
                'resultType': 'core',  # Get full metadata
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 429:
                    logger.warning("Europe PMC rate limited")
                    raise RateLimitError("Europe PMC API rate limited")
                elif response.status != 200:
                    logger.error(f"Europe PMC API error: {response.status}")
                    return []

                data = await response.json()
                return self._parse_response(data)

        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Error searching Europe PMC: {e}")
            return []

    def _parse_response(self, data: Dict[str, Any]) -> List[DiscoveredPaper]:
        """Parse Europe PMC API response."""
        papers = []
        result_list = data.get('resultList', {}).get('result', [])

        for item in result_list:
            try:
                title = (item.get('title') or '').strip()
                if not title:
                    continue

                # Extract authors
                authors = []
                author_string = item.get('authorString', '')
                if author_string:
                    # Split by comma or semicolon
                    authors = [a.strip() for a in re.split(r'[,;]', author_string) if a.strip()]

                abstract = (item.get('abstractText') or '').strip()

                # Year from publication date
                year = None
                pub_year = item.get('pubYear')
                if pub_year:
                    try:
                        year = int(pub_year)
                    except (ValueError, TypeError):
                        pass

                doi = item.get('doi')
                pmid = item.get('pmid')
                pmcid = item.get('pmcid')

                # Build URL - prefer DOI, then PMC, then PubMed
                url = None
                if doi:
                    url = f"https://doi.org/{doi}"
                elif pmcid:
                    url = f"https://europepmc.org/article/PMC/{pmcid}"
                elif pmid:
                    url = f"https://europepmc.org/article/MED/{pmid}"

                # Check for open access and PDF
                is_open_access = item.get('isOpenAccess') == 'Y'
                pdf_url = None
                if pmcid:
                    # PMC articles usually have PDF available
                    pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"

                journal = item.get('journalTitle')

                papers.append(DiscoveredPaper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    doi=doi,
                    url=url,
                    source=self.get_source_name(),
                    journal=journal,
                    is_open_access=is_open_access,
                    pdf_url=pdf_url,
                ))
            except Exception as e:
                logger.debug(f"Error parsing Europe PMC result: {e}")
                continue

        return papers
