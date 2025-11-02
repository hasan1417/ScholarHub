"""
Enhanced Paper Access Service with University SSO and Multi-tier Fallbacks
"""

import aiohttp
import asyncio
import re
import logging
from typing import Optional, Dict, List, Tuple
from urllib.parse import quote, urlparse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class PaperAccessResult(BaseModel):
    success: bool
    content_type: str  # 'pdf', 'html', 'redirect', 'authenticated_access', 'blocked'
    pdf_url: Optional[str] = None
    access_method: Optional[str] = None  # 'direct', 'university_sso', 'alternative_archive', 'pdf_redirect'
    authentication_required: bool = False
    sso_login_url: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None
    suggestions: List[str] = []

class EnhancedPaperAccessService:
    """
    Enhanced service for accessing academic papers with multiple fallback strategies
    """
    
    def __init__(self):
        self.user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        # University domains that typically support SSO
        self.university_domains = {
            'ieee.org': 'IEEE Xplore',
            'acm.org': 'ACM Digital Library',
            'springer.com': 'SpringerLink',
            'sciencedirect.com': 'ScienceDirect',
            'wiley.com': 'Wiley Online Library',
            'nature.com': 'Nature',
            'science.org': 'Science/AAAS',
            'jstor.org': 'JSTOR',
            'pubmed.ncbi.nlm.nih.gov': 'PubMed',
            'ncbi.nlm.nih.gov': 'NCBI'
        }
        
        # Alternative access sources with priorities
        self.alternative_sources = [
            {
                'name': 'Sci-Hub (Mirror 1)',
                'base_url': 'https://sci-hub.se/',
                'search_pattern': '{doi}',
                'type': 'doi_only'
            },
            {
                'name': 'LibGen Scientific',
                'base_url': 'https://libgen.is/scimag/?q=',
                'search_pattern': '{query}',
                'type': 'flexible'
            },
            {
                'name': 'Anna\'s Archive',
                'base_url': 'https://annas-archive.org/search?q=',
                'search_pattern': '{query}',
                'type': 'flexible'
            }
        ]

    async def access_paper(self, url: str, title: str = "") -> PaperAccessResult:
        """
        Main method to access a paper using multiple strategies
        """
        logger.info(f"🔍 Starting enhanced paper access for: {url}")
        
        # Strategy 1: Direct access (might work for open access or if user is authenticated)
        direct_result = await self._try_direct_access(url, title)
        if direct_result.success:
            return direct_result
            
        # Strategy 2: Check for university SSO authentication
        if direct_result.authentication_required:
            return direct_result  # Return SSO info to user
            
        # Strategy 3: Look for PDF redirects and alternative URLs
        pdf_redirect = await self._find_pdf_redirects(url, title)
        if pdf_redirect.success:
            return pdf_redirect
            
        # Strategy 4: Try alternative archives (Anna's, LibGen, etc.)
        alternative_result = await self._try_alternative_archives(url, title)
        if alternative_result.success:
            return alternative_result
            
        # Strategy 5: Return helpful information about access options
        return await self._generate_access_suggestions(url, title, direct_result)

    async def _try_direct_access(self, url: str, title: str) -> PaperAccessResult:
        """
        Try direct access to the paper URL
        """
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as response:
                    logger.info(f"📡 Direct access status: {response.status} for {url}")
                    
                    if response.status == 200:
                        content_type = response.headers.get('content-type', '').lower()
                        
                        if 'pdf' in content_type:
                            return PaperAccessResult(
                                success=True,
                                content_type='pdf',
                                pdf_url=url,
                                access_method='direct',
                                title=title
                            )
                        else:
                            # Check if this is HTML that might contain PDF links
                            html_content = await response.text()
                            pdf_links = await self._extract_pdf_links(html_content, url)
                            
                            if pdf_links:
                                return PaperAccessResult(
                                    success=True,
                                    content_type='pdf',
                                    pdf_url=pdf_links[0],
                                    access_method='pdf_redirect',
                                    title=title
                                )
                    
                    elif response.status == 302 or response.status == 301:
                        # Follow redirects manually to see where they lead
                        redirect_url = response.headers.get('Location')
                        if redirect_url:
                            return await self._try_direct_access(redirect_url, title)
                    
                    elif response.status == 403 or response.status == 401:
                        # Check if this requires university authentication
                        html_content = await response.text()
                        sso_info = await self._detect_sso_authentication(html_content, url)
                        
                        if sso_info:
                            return PaperAccessResult(
                                success=False,
                                content_type='authenticated_access',
                                authentication_required=True,
                                sso_login_url=sso_info,
                                access_method='university_sso',
                                title=title,
                                error="University SSO authentication detected"
                            )
                        
        except Exception as e:
            logger.debug(f"Direct access failed: {e}")
        
        return PaperAccessResult(
            success=False,
            content_type='blocked',
            title=title
        )

    async def _detect_sso_authentication(self, html_content: str, original_url: str) -> Optional[str]:
        """
        Detect if the page requires university SSO authentication and provide KFUPM-specific access
        """
        # First check for KFUPM proxy access
        from app.services.university_proxy_access import UniversityProxyService
        proxy_service = UniversityProxyService()
        
        # Generate KFUPM proxy URL if available
        kfupm_url = proxy_service.generate_university_url(original_url)
        if kfupm_url:
            logger.info(f"🏫 Generated KFUPM proxy URL: {kfupm_url}")
            return kfupm_url
        
        # Common SSO indicators
        sso_indicators = [
            r'shibboleth',
            r'institutional.*login',
            r'university.*access',
            r'library.*login',
            r'athens.*authentication',
            r'federated.*login',
            r'sign.*in.*through.*your.*institution',
            r'access.*through.*your.*library'
        ]
        
        html_lower = html_content.lower()
        
        for indicator in sso_indicators:
            if re.search(indicator, html_lower):
                # For KFUPM users, provide the library portal
                if any(domain in original_url for domain in ['ieee.org', 'springer.com', 'sciencedirect.com', 'wiley.com']):
                    return "https://library-web.kfupm.edu.sa/e-resources/online-databases/"
                
                # Try to find the actual SSO login URL
                login_patterns = [
                    r'href=[\'"]([^\'\"]*shibboleth[^\'\"]*)[\'"]',
                    r'href=[\'"]([^\'\"]*institutional[^\'\"]*login[^\'\"]*)[\'"]',
                    r'href=[\'"]([^\'\"]*athens[^\'\"]*)[\'"]',
                ]
                
                for pattern in login_patterns:
                    matches = re.findall(pattern, html_content, re.IGNORECASE)
                    if matches:
                        login_url = matches[0]
                        if not login_url.startswith('http'):
                            # Convert relative URL to absolute
                            from urllib.parse import urljoin
                            login_url = urljoin(original_url, login_url)
                        return login_url
                
                # If we can't find specific login URL, return KFUPM library portal
                return "https://library-web.kfupm.edu.sa/e-resources/online-databases/"
                
        return None

    async def _find_pdf_redirects(self, url: str, title: str) -> PaperAccessResult:
        """
        Look for PDF download links or redirects on the paper page
        """
        try:
            headers = {'User-Agent': self.user_agent}
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        html_content = await response.text()
                        
                        # Look for PDF download links
                        pdf_patterns = [
                            r'href=[\'"]([^\'\"]*\.pdf[^\'\"]*)[\'"]',
                            r'href=[\'"]([^\'\"]*download[^\'\"]*pdf[^\'\"]*)[\'"]',
                            r'href=[\'"]([^\'\"]*viewPDF[^\'\"]*)[\'"]',
                            r'href=[\'"]([^\'\"]*fulltext[^\'\"]*pdf[^\'\"]*)[\'"]',
                        ]
                        
                        for pattern in pdf_patterns:
                            matches = re.findall(pattern, html_content, re.IGNORECASE)
                            for match in matches:
                                if not match.startswith('http'):
                                    from urllib.parse import urljoin
                                    match = urljoin(url, match)
                                
                                # Verify this is actually a PDF
                                if await self._verify_pdf_url(match, session):
                                    return PaperAccessResult(
                                        success=True,
                                        content_type='pdf',
                                        pdf_url=match,
                                        access_method='pdf_redirect',
                                        title=title
                                    )
        
        except Exception as e:
            logger.debug(f"PDF redirect search failed: {e}")
        
        return PaperAccessResult(success=False, content_type='blocked', title=title)

    async def _verify_pdf_url(self, url: str, session: aiohttp.ClientSession) -> bool:
        """
        Verify that a URL actually points to a PDF
        """
        try:
            async with session.head(url, timeout=5) as response:
                content_type = response.headers.get('content-type', '').lower()
                return 'pdf' in content_type or url.lower().endswith('.pdf')
        except:
            return False

    async def _extract_pdf_links(self, html_content: str, base_url: str) -> List[str]:
        """
        Extract PDF links from HTML content
        """
        pdf_links = []
        
        # Enhanced PDF link patterns
        patterns = [
            r'href=[\'"]([^\'\"]*\.pdf[^\'\"]*)[\'"]',
            r'href=[\'"]([^\'\"]*download[^\'\"]*)[\'"].*pdf',
            r'href=[\'"]([^\'\"]*viewPDF[^\'\"]*)[\'"]',
            r'data-pdf-url=[\'"]([^\'\"]*)[\'"]',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                if not match.startswith('http'):
                    from urllib.parse import urljoin
                    match = urljoin(base_url, match)
                pdf_links.append(match)
        
        return list(set(pdf_links))  # Remove duplicates

    async def _try_alternative_archives(self, url: str, title: str) -> PaperAccessResult:
        """
        Try alternative archives like Anna's Archive, LibGen, etc.
        """
        from app.core.config import settings
        
        if not settings.ENABLE_ALTERNATIVE_ACCESS:
            return PaperAccessResult(
                success=False,
                content_type='blocked',
                error="Alternative access disabled",
                title=title
            )
        
        # Extract DOI for better searching
        doi = self._extract_doi(url, title)
        
        # Prepare search queries
        search_queries = []
        if doi:
            search_queries.append(doi)
        if title and len(title.strip()) > 10:
            # Clean title for searching
            clean_title = re.sub(r'[^\w\s]', ' ', title)
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            search_queries.append(clean_title)
        
        if not search_queries:
            return PaperAccessResult(
                success=False,
                content_type='blocked',
                error="No searchable identifiers found",
                title=title
            )
        
        # Try each alternative source
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {'User-Agent': self.user_agent}
            
            for source in self.alternative_sources:
                for query in search_queries:
                    try:
                        if source['type'] == 'doi_only' and not doi:
                            continue
                        
                        search_url = source['base_url'] + quote(query)
                        logger.info(f"🔍 Searching {source['name']} for: {query[:50]}...")
                        
                        async with session.get(search_url, headers=headers, timeout=8) as response:
                            if response.status == 200:
                                content = await response.text()
                                pdf_url = await self._extract_archive_pdf_url(content, source['name'], session, headers)
                                
                                if pdf_url:
                                    query_type = "DOI" if query == doi else "title"
                                    return PaperAccessResult(
                                        success=True,
                                        content_type='pdf',
                                        pdf_url=pdf_url,
                                        access_method='alternative_archive',
                                        title=title,
                                        error=f"Found via {source['name']} using {query_type} search (demonstration only)"
                                    )
                                    
                    except Exception as e:
                        logger.debug(f"{source['name']} search failed: {e}")
                        continue
        
        return PaperAccessResult(
            success=False,
            content_type='blocked',
            error="Not found in alternative archives",
            title=title
        )

    async def _extract_archive_pdf_url(self, html_content: str, source_name: str, session: aiohttp.ClientSession, headers: dict) -> Optional[str]:
        """
        Extract PDF URL from alternative archive search results
        """
        if 'libgen' in source_name.lower():
            return await self._extract_libgen_pdf_url(html_content, session, headers)
        elif 'anna' in source_name.lower():
            return await self._extract_annas_pdf_url(html_content, session, headers)
        elif 'sci-hub' in source_name.lower():
            return await self._extract_scihub_pdf_url(html_content)
        
        return None

    async def _extract_libgen_pdf_url(self, html_content: str, session: aiohttp.ClientSession, headers: dict) -> Optional[str]:
        """Extract PDF URL from LibGen results"""
        # Look for download links
        download_patterns = [
            r'href="([^"]*download[^"]*\.php[^"]*)"',
            r'href="([^"]*library\.lol[^"]*)"',
            r'href="([^"]*libgen\.[^"]*download[^"]*)"',
        ]
        
        for pattern in download_patterns:
            matches = re.findall(pattern, html_content)
            for match in matches:
                if match.startswith('http'):
                    return match
                else:
                    return f"https://libgen.is{match}"
        
        return None

    async def _extract_annas_pdf_url(self, html_content: str, session: aiohttp.ClientSession, headers: dict) -> Optional[str]:
        """Extract PDF URL from Anna's Archive results"""
        # Look for download links
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for download buttons or links
            download_links = soup.find_all('a', href=True)
            for link in download_links:
                href = link.get('href', '')
                text = link.get_text().lower()
                
                if any(word in text for word in ['download', 'pdf', 'get']):
                    if href.startswith('http'):
                        return href
                    elif href.startswith('/'):
                        return f"https://annas-archive.org{href}"
                        
        except ImportError:
            # Fallback to regex if BeautifulSoup not available
            pdf_patterns = [
                r'href="([^"]*download[^"]*)"',
                r'href="([^"]*/md5/[^"]*)"',
                r'href="([^"]*/doi/[^"]*)"',
            ]
            
            for pattern in pdf_patterns:
                matches = re.findall(pattern, html_content)
                for match in matches:
                    if match.startswith('http'):
                        return match
                    else:
                        return f"https://annas-archive.org{match}"
        
        return None

    async def _extract_scihub_pdf_url(self, html_content: str) -> Optional[str]:
        """Extract PDF URL from Sci-Hub results"""
        # Sci-Hub usually embeds PDFs directly
        pdf_patterns = [
            r'src="([^"]*\.pdf[^"]*)"',
            r'href="([^"]*\.pdf[^"]*)"',
            r'"(https?://[^"]*\.pdf[^"]*)"',
        ]
        
        for pattern in pdf_patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                return matches[0]
        
        return None

    def _extract_doi(self, url: str, title: str) -> Optional[str]:
        """
        Extract DOI from URL or title
        """
        # URL patterns
        url_patterns = [
            r'doi\.org/(.+)',
            r'dx\.doi\.org/(.+)',
            r'/doi/abs?/?(10\.\d+/[^/?]+)',
            r'arxiv\.org/abs/(\d+\.\d+)',
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                doi = match.group(1)
                if self._is_valid_doi_format(doi):
                    return doi
        
        # Title patterns
        if title:
            title_patterns = [
                r'DOI:?\s*(10\.\d+/[^\s,;]+)',
                r'doi:?\s*(10\.\d+/[^\s,;]+)',
                r'(10\.\d+/[^\s,;]+)',
            ]
            
            for pattern in title_patterns:
                matches = re.findall(pattern, title, re.IGNORECASE)
                for match in matches:
                    if self._is_valid_doi_format(match):
                        return match
        
        return None

    def _is_valid_doi_format(self, doi: str) -> bool:
        """Validate DOI format"""
        if not doi or len(doi) < 7:
            return False
        
        # ArXiv IDs
        if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', doi):
            return True
        
        # Standard DOIs
        return bool(re.match(r'^10\.\d+/.+$', doi))

    async def _generate_access_suggestions(self, url: str, title: str, direct_result: PaperAccessResult) -> PaperAccessResult:
        """
        Generate helpful suggestions when access fails
        """
        suggestions = []
        domain = urlparse(url).netloc.lower()
        
        # Domain-specific suggestions
        if 'sciencedirect.com' in domain:
            suggestions.extend([
                "Try accessing through your university library's ScienceDirect subscription",
                "Search for the paper title on Google Scholar for open access versions",
                "Check if the authors have deposited a preprint on arXiv or institutional repository"
            ])
        elif 'ieee.org' in domain:
            suggestions.extend([
                "Access through your university's IEEE Xplore subscription",
                "Look for author's preprint versions on their personal website",
                "Check arXiv.org for preprint versions"
            ])
        elif 'nature.com' in domain or 'science.org' in domain:
            suggestions.extend([
                "Access through university library subscription",
                "Check PubMed Central for open access version",
                "Look for author's institutional repository deposit"
            ])
        else:
            suggestions.extend([
                "Try accessing through your university library",
                "Search for open access versions on Google Scholar",
                "Check author's personal website or institutional repository"
            ])
        
        # Add general suggestions
        suggestions.extend([
            "Contact the authors directly for a copy of the paper",
            "Use interlibrary loan services if available",
            "Check if a preprint version exists on arXiv, bioRxiv, or other preprint servers"
        ])
        
        error_msg = "Paper content is not publicly accessible."
        if direct_result.authentication_required:
            error_msg += " University SSO authentication may be required."
        
        return PaperAccessResult(
            success=False,
            content_type='blocked',
            authentication_required=direct_result.authentication_required,
            sso_login_url=direct_result.sso_login_url,
            title=title,
            error=error_msg,
            suggestions=suggestions[:5]  # Limit to top 5 suggestions
        )