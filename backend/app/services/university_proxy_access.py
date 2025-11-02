"""
University Proxy Access Service - Leverages Browser Session Authentication
This system works WITH your university authentication rather than bypassing it.
"""

import aiohttp
import asyncio
import re
import logging
from typing import Optional, Dict, List, Tuple
from urllib.parse import quote, urlparse, urljoin
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class UniversityAccessConfig(BaseModel):
    """Configuration for university access"""
    university_name: str = "KFUPM"
    library_base_url: str = "https://library-web.kfupm.edu.sa"
    proxy_patterns: List[str] = [
        "https://ieeexplore-ieee-org.sdl.idm.oclc.org",
        "https://link-springer-com.sdl.idm.oclc.org", 
        "https://www-sciencedirect-com.sdl.idm.oclc.org",
        "https://onlinelibrary-wiley-com.sdl.idm.oclc.org"
    ]
    
class UniversityProxyService:
    """
    Service that helps users access papers through university authentication
    Rather than storing credentials, it guides users to authenticate in browser
    """
    
    def __init__(self):
        self.config = UniversityAccessConfig()
        # Mapping of publisher domains to KFUPM proxy base host
        # Updated to use kfupm.idm.oclc.org as provided.
        self.university_mappings = {
            'ieeexplore.ieee.org': 'https://ieeexplore-ieee-org.kfupm.idm.oclc.org',
            'ieee.org': 'https://ieeexplore-ieee-org.kfupm.idm.oclc.org',
            'link.springer.com': 'https://link-springer-com.kfupm.idm.oclc.org',
            'springer.com': 'https://link-springer-com.kfupm.idm.oclc.org',
            # Keep prior defaults for other providers until KFUPM bases are confirmed
            'www.sciencedirect.com': 'https://www-sciencedirect-com.sdl.idm.oclc.org',
            'sciencedirect.com': 'https://www-sciencedirect-com.sdl.idm.oclc.org',
            'onlinelibrary.wiley.com': 'https://onlinelibrary-wiley-com.sdl.idm.oclc.org',
            'wiley.com': 'https://onlinelibrary-wiley-com.sdl.idm.oclc.org',
            'nature.com': 'https://www-nature-com.sdl.idm.oclc.org',
            'www.nature.com': 'https://www-nature-com.sdl.idm.oclc.org',
            'science.org': 'https://www-science-org.sdl.idm.oclc.org',
            'www.science.org': 'https://www-science-org.sdl.idm.oclc.org',
            'dl.acm.org': 'https://dl-acm-org.sdl.idm.oclc.org',
        }

        # Provider search URL patterns. Value is a tuple (display_name, search_url_template)
        # Templates may use {query} or {doi} placeholders.
        self.provider_search_patterns = {
            'ieeexplore.ieee.org': (
                'IEEE Xplore',
                'https://ieeexplore-ieee-org.kfupm.idm.oclc.org/search/searchresult.jsp?newsearch=true&queryText={query}'
            ),
            'link.springer.com': (
                'SpringerLink',
                'https://link-springer-com.kfupm.idm.oclc.org/search?query={query}'
            ),
            'www.sciencedirect.com': (
                'ScienceDirect',
                'https://www-sciencedirect-com.sdl.idm.oclc.org/search?qs={query}'
            ),
            'onlinelibrary.wiley.com': (
                'Wiley Online Library',
                'https://onlinelibrary-wiley-com.sdl.idm.oclc.org/action/doSearch?AllField={query}'
            ),
            'www.nature.com': (
                'Nature',
                'https://www-nature-com.sdl.idm.oclc.org/search?q={query}'
            ),
            'www.science.org': (
                'Science/AAAS',
                'https://www-science-org.sdl.idm.oclc.org/action/doSearch?AllField={query}'
            ),
            'dl.acm.org': (
                'ACM Digital Library',
                'https://dl-acm-org.sdl.idm.oclc.org/action/doSearch?AllField={query}'
            ),
        }
    
    def generate_university_url(self, original_url: str) -> Optional[str]:
        """
        Convert a regular academic URL to the university proxy URL
        """
        try:
            parsed = urlparse(original_url)
            domain = parsed.netloc.lower()
            
            # Check if we have a proxy mapping for this domain
            for original_domain, proxy_base in self.university_mappings.items():
                if original_domain in domain:
                    # Construct the proxied URL
                    proxied_url = original_url.replace(f"https://{parsed.netloc}", proxy_base)
                    logger.info(f"🏫 Generated KFUPM proxy URL: {proxied_url}")
                    return proxied_url
            
            return None
        except Exception as e:
            logger.error(f"Error generating university URL: {e}")
            return None
    
    def get_university_access_instructions(self, url: str) -> Dict[str, str]:
        """
        Generate step-by-step instructions for accessing papers through university
        """
        domain = urlparse(url).netloc.lower()
        proxied_url = self.generate_university_url(url)
        
        base_instructions = {
            "step1": "🏫 Access through KFUPM Library",
            "step2": "1. Open the KFUPM library link in a new tab",
            "step3": "2. Login with your KFUPM credentials if prompted", 
            "step4": "3. The paper should be accessible through your subscription",
            "library_url": "https://library-web.kfupm.edu.sa/e-resources/online-databases/",
            "direct_access": proxied_url if proxied_url else None
        }
        
        # Publisher-specific instructions
        if 'ieee' in domain:
            base_instructions.update({
                "publisher": "IEEE Xplore",
                "specific_tip": "Look for 'IEEE Xplore Digital Library' in your university resources",
                "search_tip": "You can also search for the paper directly in IEEE Xplore after logging in"
            })
        elif 'sciencedirect' in domain:
            base_instructions.update({
                "publisher": "ScienceDirect (Elsevier)", 
                "specific_tip": "Look for 'ScienceDirect' or 'Elsevier' in your university resources",
                "search_tip": "Use the DOI or paper title to search within ScienceDirect"
            })
        elif 'springer' in domain:
            base_instructions.update({
                "publisher": "SpringerLink",
                "specific_tip": "Look for 'Springer' or 'SpringerLink' in your university resources",
                "search_tip": "Search by journal name and article title"
            })
        elif 'wiley' in domain:
            base_instructions.update({
                "publisher": "Wiley Online Library",
                "specific_tip": "Look for 'Wiley' in your university resources", 
                "search_tip": "Use journal name and DOI for precise search"
            })
        
        return base_instructions

    def build_provider_search_urls(self, title: Optional[str] = None, doi: Optional[str] = None) -> List[Dict[str, str]]:
        """Build proxied provider search URLs using title or DOI as query.

        The returned list includes provider name and proxied search URL, which the user can open
        after authenticating via KFUPM.
        """
        query = (doi or '') if doi else (title or '')
        if not query:
            return []
        from urllib.parse import quote_plus
        q = quote_plus(query)
        links: List[Dict[str, str]] = []
        for domain, (name, tmpl) in self.provider_search_patterns.items():
            url = tmpl.format(query=q, doi=q)
            proxied = self.university_mappings.get(domain)
            if proxied:
                # Convert template host to proxied host
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    proxied_url = url.replace(f"{parsed.scheme}://{parsed.netloc}", proxied)
                except Exception:
                    proxied_url = url
            else:
                proxied_url = url
            links.append({
                'provider': name,
                'url': proxied_url
            })
        return links
    
    async def check_university_access_status(self, url: str) -> Dict[str, any]:
        """
        Check if a URL is likely to work through university access
        """
        domain = urlparse(url).netloc.lower()
        proxied_url = self.generate_university_url(url)
        
        # Check if this is a known university-accessible resource
        is_university_resource = any(univ_domain in domain for univ_domain in self.university_mappings.keys())
        
        confidence_score = 0.0
        if is_university_resource:
            confidence_score = 0.9  # High confidence for known resources
        elif any(keyword in domain for keyword in ['ieee', 'springer', 'elsevier', 'wiley', 'nature', 'science']):
            confidence_score = 0.7  # Medium-high confidence for major publishers
        elif 'doi.org' in url:
            confidence_score = 0.6  # Medium confidence for DOI links
        else:
            confidence_score = 0.3  # Low confidence for unknown domains
        
        return {
            "has_university_access": is_university_resource,
            "confidence_score": confidence_score,
            "proxied_url": proxied_url,
            "publisher": self._identify_publisher(domain),
            "access_method": "university_proxy" if proxied_url else "manual_search"
        }
    
    def _identify_publisher(self, domain: str) -> str:
        """Identify the publisher from domain"""
        publishers = {
            'ieee': 'IEEE',
            'springer': 'Springer',
            'elsevier': 'Elsevier',
            'sciencedirect': 'Elsevier/ScienceDirect',
            'wiley': 'Wiley',
            'nature': 'Nature Publishing Group',
            'science': 'AAAS/Science',
            'acm': 'ACM',
            'jstor': 'JSTOR'
        }
        
        for key, publisher in publishers.items():
            if key in domain:
                return publisher
        
        return "Unknown Publisher"

class UniversityAuthenticationGuide:
    """
    Provides interactive guidance for university authentication
    """
    
    @staticmethod
    def create_authentication_flow(paper_url: str, paper_title: str = "") -> Dict[str, any]:
        """
        Create a step-by-step authentication flow for university access
        """
        service = UniversityProxyService()
        access_info = service.get_university_access_instructions(paper_url)
        
        return {
            "authentication_type": "university_guided",
            "university": "KFUPM",
            "paper_title": paper_title,
            "paper_url": paper_url,
            "instructions": access_info,
            "quick_access_url": access_info.get("direct_access"),
            "fallback_url": access_info.get("library_url"),
            "estimated_success_rate": "95%",  # High for university resources
            "requires_vpn": False,  # KFUPM library access doesn't typically require VPN
            "help_text": "If you encounter issues, contact KFUPM Library Support"
        }
