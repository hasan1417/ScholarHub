"""Metadata enrichers used during discovery."""

from __future__ import annotations

import asyncio
import logging
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
