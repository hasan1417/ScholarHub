#!/usr/bin/env python3
"""
Demo script to show alternative access working with mock data
This creates a simple endpoint that always succeeds for demonstration
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

# This is for demonstration only
demo_router = APIRouter()

class DemoPaperContentRequest(BaseModel):
    url: str
    paper_title: Optional[str] = None

class DemoPaperContentResponse(BaseModel):
    success: bool
    content_type: str
    title: Optional[str] = None
    pdf_url: Optional[str] = None
    error: Optional[str] = None

@demo_router.post("/demo/papers/content", response_model=DemoPaperContentResponse)
async def demo_fetch_paper_content(request: DemoPaperContentRequest):
    """
    Demo endpoint that simulates successful alternative access
    This always returns a successful response for demonstration purposes
    """
    
    # Simulate different responses based on URL
    if 'arxiv.org' in request.url:
        return DemoPaperContentResponse(
            success=True,
            content_type="pdf",
            title=request.paper_title,
            pdf_url=request.url.replace('/abs/', '/pdf/') + '.pdf',
            error="ArXiv paper - direct PDF access available"
        )
    elif 'doi.org' in request.url or 'sciencedirect.com' in request.url:
        # Simulate successful alternative access for DOI papers
        return DemoPaperContentResponse(
            success=True,
            content_type="pdf",
            title=request.paper_title,
            pdf_url="https://example.com/demo-paper.pdf",  # Demo URL
            error="Found via LibGen (libgen.is) using DOI search (demonstration only)"
        )
    else:
        # Simulate title-based search success
        return DemoPaperContentResponse(
            success=True,
            content_type="pdf",
            title=request.paper_title,
            pdf_url="https://example.com/demo-paper-title.pdf",  # Demo URL
            error="Found via Anna's Archive (annas-archive.org) using title search (demonstration only)"
        )

print("🎭 Demo Alternative Access Endpoint Created")
print("Add this to your main.py to test:")
print("app.include_router(demo_router, prefix='/api/v1')")