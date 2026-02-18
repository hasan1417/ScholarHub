// ScholarHub Browser Extension - Content Script
// Extracts paper metadata from supported academic sites.

(function () {
  'use strict';

  // Avoid double-injection
  if (window.__scholarHubContentLoaded) return;
  window.__scholarHubContentLoaded = true;

  let detectedPaper = null;

  // ── Extraction entry point ──

  function detectPaper() {
    const host = location.hostname;
    const url = location.href;

    if (host.includes('scholar.google')) {
      detectedPaper = extractGoogleScholar();
    } else if (host.includes('pubmed.ncbi.nlm.nih.gov')) {
      detectedPaper = extractPubMed();
    } else if (host.includes('arxiv.org')) {
      detectedPaper = extractArXiv();
    } else if (host.includes('doi.org') || host.includes('dx.doi.org')) {
      detectedPaper = extractDOIPage();
    } else {
      // Generic journal extraction (Nature, Springer, IEEE, ACM, Wiley, ScienceDirect)
      detectedPaper = extractFromMetaTags();
    }

    // Fill in current URL if missing
    if (detectedPaper && !detectedPaper.url) {
      detectedPaper.url = url;
    }

    // Clean up fields
    if (detectedPaper) {
      detectedPaper.title = clean(detectedPaper.title);
      if (detectedPaper.abstract) {
        detectedPaper.abstract = clean(detectedPaper.abstract);
      }
      if (detectedPaper.authors) {
        detectedPaper.authors = detectedPaper.authors.map(clean).filter(Boolean);
      }
    }

    if (detectedPaper && !detectedPaper.pdfUrl) {
      detectedPaper.pdfUrl = getMeta('citation_pdf_url') || scanForPdfLink() || null;
    }

    if (detectedPaper && detectedPaper.title) {
      // Only show the badge if the user is authenticated
      chrome.storage.local.get(['accessToken'], (result) => {
        if (result.accessToken) {
          showBadge();
        }
      });
    }

    return detectedPaper;
  }

  // ── Site-specific extractors ──

  function extractGoogleScholar() {
    // On a search results page, detect the first result or a focused result
    const resultEl = document.querySelector('.gs_r.gs_or.gs_scl');
    if (!resultEl) return null;

    const titleEl = resultEl.querySelector('.gs_rt a') || resultEl.querySelector('.gs_rt');
    const title = titleEl ? titleEl.textContent : null;
    if (!title) return null;

    const metaEl = resultEl.querySelector('.gs_a');
    let authors = [];
    let year = null;
    let journal = null;

    if (metaEl) {
      const metaText = metaEl.textContent;
      // Format: "Author1, Author2 - Journal, Year - Publisher"
      const parts = metaText.split(' - ');
      if (parts.length >= 1) {
        authors = parts[0].split(',').map((a) => a.trim()).filter(Boolean);
      }
      // Extract year (4-digit number)
      const yearMatch = metaText.match(/\b(19|20)\d{2}\b/);
      if (yearMatch) year = parseInt(yearMatch[0], 10);

      if (parts.length >= 2) {
        journal = parts[1].replace(/,?\s*\d{4}.*$/, '').trim() || null;
      }
    }

    const linkEl = resultEl.querySelector('.gs_rt a');
    const url = linkEl ? linkEl.href : null;

    const pdfLink = resultEl.querySelector('.gs_or_ggsm a, .gs_ggsd a');
    const pdfUrl = pdfLink ? pdfLink.href : null;

    return { title, authors, year, journal, url, doi: null, abstract: null, pdfUrl, source: 'Google Scholar' };
  }

  function extractPubMed() {
    const titleEl = document.querySelector('.heading-title') || document.querySelector('h1.heading-title');
    const title = titleEl ? titleEl.textContent : null;
    if (!title) return null;

    // Authors
    const authorEls = document.querySelectorAll('.authors-list .full-name, .authors-list a.full-name');
    const authors = Array.from(authorEls).map((el) => el.textContent.trim());

    // DOI
    let doi = null;
    const doiEl = document.querySelector('.id-link[href*="doi.org"]') || document.querySelector('a[data-ga-action="DOI"]');
    if (doiEl) {
      const doiHref = doiEl.href || doiEl.textContent;
      const doiMatch = doiHref.match(/10\.\d{4,}\/[^\s]+/);
      if (doiMatch) doi = doiMatch[0];
    }

    // Abstract
    const abstractEl = document.querySelector('.abstract-content p') || document.querySelector('#abstract .abstract-content');
    const abstract = abstractEl ? abstractEl.textContent : null;

    // Year
    let year = null;
    const dateEl = document.querySelector('.cit time') || document.querySelector('.article-source time');
    if (dateEl) {
      const yearMatch = (dateEl.textContent || dateEl.getAttribute('datetime') || '').match(/\b(19|20)\d{2}\b/);
      if (yearMatch) year = parseInt(yearMatch[0], 10);
    }

    // Journal
    let journal = null;
    const journalEl = document.querySelector('.journal-actions button[title]') || document.querySelector('#full-view-journal-trigger');
    if (journalEl) {
      journal = journalEl.getAttribute('title') || journalEl.textContent.trim();
    }

    const pdfUrl = getMeta('citation_pdf_url') || null;

    return { title, authors, year, doi, url: location.href, abstract, journal, pdfUrl, source: 'PubMed' };
  }

  function extractArXiv() {
    // Abstract page: /abs/XXXX.XXXXX
    const titleEl = document.querySelector('.title.mathjax');
    let title = titleEl ? titleEl.textContent : null;
    if (title) {
      title = title.replace(/^Title:\s*/i, '');
    }
    if (!title) return null;

    const authorsEl = document.querySelector('.authors');
    let authors = [];
    if (authorsEl) {
      const authorLinks = authorsEl.querySelectorAll('a');
      if (authorLinks.length > 0) {
        authors = Array.from(authorLinks).map((a) => a.textContent.trim());
      } else {
        authors = authorsEl.textContent.replace(/^Authors?:\s*/i, '').split(',').map((a) => a.trim()).filter(Boolean);
      }
    }

    const abstractEl = document.querySelector('.abstract.mathjax');
    let abstract = abstractEl ? abstractEl.textContent : null;
    if (abstract) {
      abstract = abstract.replace(/^Abstract:\s*/i, '');
    }

    // arXiv ID from URL
    const arxivMatch = location.pathname.match(/\/(?:abs|pdf)\/(\d{4}\.\d{4,5}(?:v\d+)?)/);
    const arxivId = arxivMatch ? arxivMatch[1] : null;

    // Year from submission date or ID
    let year = null;
    const dateEl = document.querySelector('.dateline');
    if (dateEl) {
      const yearMatch = dateEl.textContent.match(/\b(19|20)\d{2}\b/);
      if (yearMatch) year = parseInt(yearMatch[0], 10);
    }
    if (!year && arxivId) {
      const prefix = arxivId.substring(0, 2);
      const century = parseInt(prefix, 10) > 90 ? '19' : '20';
      year = parseInt(century + prefix, 10);
    }

    // DOI if present
    let doi = null;
    const doiEl = document.querySelector('td.doi a') || document.querySelector('a[href*="doi.org"]');
    if (doiEl) {
      const doiMatch = (doiEl.href || doiEl.textContent).match(/10\.\d{4,}\/[^\s]+/);
      if (doiMatch) doi = doiMatch[0];
    }

    const pdfUrl = arxivId ? `https://arxiv.org/pdf/${arxivId}.pdf` : null;

    return {
      title,
      authors,
      year,
      doi,
      url: location.href,
      abstract,
      journal: arxivId ? `arXiv:${arxivId}` : 'arXiv',
      pdfUrl,
      source: 'arXiv',
    };
  }

  function extractDOIPage() {
    // DOI pages typically redirect. Extract DOI from URL and metadata from meta tags.
    let doi = null;
    const doiMatch = location.href.match(/doi\.org\/(10\.\d{4,}\/[^\s?#]+)/);
    if (doiMatch) doi = doiMatch[1];

    const meta = extractFromMetaTags();
    if (meta) {
      if (doi && !meta.doi) meta.doi = doi;
      meta.source = meta.source || 'DOI';
      return meta;
    }

    // Fallback: minimal extraction from page title
    const title = document.title || null;
    if (!title) return null;

    return { title, authors: [], year: null, doi, url: location.href, abstract: null, journal: null, source: 'DOI' };
  }

  /**
   * Generic extractor using <meta> citation tags.
   * Works for Nature, Springer, IEEE, ACM, Wiley, ScienceDirect, and most journal sites.
   */
  function extractFromMetaTags() {
    const title = getMeta('citation_title') || getMeta('DC.title') || getMeta('og:title') || getMeta('dc.title');
    if (!title) return null;

    // Authors: citation_author can appear multiple times
    const authorMetas = document.querySelectorAll('meta[name="citation_author"]');
    let authors = Array.from(authorMetas).map((m) => m.getAttribute('content')).filter(Boolean);
    if (authors.length === 0) {
      const dcCreator = document.querySelectorAll('meta[name="DC.creator"], meta[name="dc.creator"]');
      authors = Array.from(dcCreator).map((m) => m.getAttribute('content')).filter(Boolean);
    }

    // DOI
    const doi = getMeta('citation_doi') || getMeta('DC.identifier') || getMeta('dc.identifier') || null;

    // Journal
    const journal = getMeta('citation_journal_title') || getMeta('citation_conference_title') || null;

    // Year
    let year = null;
    const dateStr = getMeta('citation_date') || getMeta('citation_publication_date') || getMeta('citation_online_date') || getMeta('DC.date') || '';
    const yearMatch = dateStr.match(/\b(19|20)\d{2}\b/);
    if (yearMatch) year = parseInt(yearMatch[0], 10);

    // Abstract
    const abstract = getMeta('citation_abstract') || getMeta('DC.description') || getMeta('description') || null;

    // Determine source from hostname
    const host = location.hostname;
    let source = 'Journal';
    if (host.includes('nature.com')) source = 'Nature';
    else if (host.includes('springer.com')) source = 'Springer';
    else if (host.includes('ieee.org')) source = 'IEEE';
    else if (host.includes('acm.org')) source = 'ACM';
    else if (host.includes('wiley.com')) source = 'Wiley';
    else if (host.includes('sciencedirect.com')) source = 'ScienceDirect';

    const pdfUrl = getMeta('citation_pdf_url') || null;

    return { title, authors, year, doi, url: location.href, abstract, journal, pdfUrl, source };
  }

  // ── Floating badge ──

  function showBadge() {
    if (document.getElementById('scholarhub-badge')) return;

    const badge = document.createElement('div');
    badge.id = 'scholarhub-badge';
    badge.title = 'Save to ScholarHub';
    badge.setAttribute('role', 'button');
    badge.setAttribute('tabindex', '0');

    // Use textContent for the SVG fallback - we create the SVG via DOM APIs
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '20');
    svg.setAttribute('height', '20');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'white');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');

    const path1 = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path1.setAttribute('d', 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20');
    const path2 = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path2.setAttribute('d', 'M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z');
    const path3 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    path3.setAttribute('x1', '12');
    path3.setAttribute('y1', '8');
    path3.setAttribute('x2', '12');
    path3.setAttribute('y2', '16');
    const path4 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    path4.setAttribute('x1', '8');
    path4.setAttribute('y1', '12');
    path4.setAttribute('x2', '16');
    path4.setAttribute('y2', '12');

    svg.appendChild(path1);
    svg.appendChild(path2);
    svg.appendChild(path3);
    svg.appendChild(path4);
    badge.appendChild(svg);

    badge.addEventListener('click', handleBadgeClick);
    badge.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') handleBadgeClick();
    });

    document.body.appendChild(badge);
  }

  async function handleBadgeClick() {
    const badge = document.getElementById('scholarhub-badge');
    if (!badge || !detectedPaper) return;

    badge.classList.add('scholarhub-badge-saving');

    try {
      const resp = await chrome.runtime.sendMessage({
        type: 'SAVE_REFERENCE',
        data: detectedPaper,
      });

      if (resp && resp.success) {
        badge.classList.remove('scholarhub-badge-saving');
        badge.classList.add('scholarhub-badge-success');
        setTimeout(() => badge.classList.remove('scholarhub-badge-success'), 3000);
      } else {
        badge.classList.remove('scholarhub-badge-saving');
        badge.classList.add('scholarhub-badge-error');
        showBadgeTooltip(badge, (resp && resp.error) || 'Failed to save reference');
        setTimeout(() => badge.classList.remove('scholarhub-badge-error'), 3000);
      }
    } catch {
      badge.classList.remove('scholarhub-badge-saving');
      badge.classList.add('scholarhub-badge-error');
      showBadgeTooltip(badge, 'Network error. Check your connection.');
      setTimeout(() => badge.classList.remove('scholarhub-badge-error'), 3000);
    }
  }

  /**
   * Show a brief tooltip near the badge with an error message, auto-dismissed after 4 seconds.
   */
  function showBadgeTooltip(badge, message) {
    // Remove any existing tooltip first
    const existing = document.getElementById('scholarhub-badge-tooltip');
    if (existing) existing.remove();

    const tooltip = document.createElement('div');
    tooltip.id = 'scholarhub-badge-tooltip';
    tooltip.textContent = message;

    // Position above and to the left of the badge
    Object.assign(tooltip.style, {
      position: 'fixed',
      bottom: '76px',
      right: '12px',
      zIndex: '2147483647',
      background: '#1f2937',
      color: '#f9fafb',
      fontSize: '13px',
      lineHeight: '1.4',
      padding: '8px 12px',
      borderRadius: '8px',
      maxWidth: '260px',
      boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
      opacity: '0',
      transition: 'opacity 0.2s ease',
      pointerEvents: 'none',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    });

    document.body.appendChild(tooltip);
    // Trigger fade-in on next frame
    requestAnimationFrame(() => { tooltip.style.opacity = '1'; });

    setTimeout(() => {
      tooltip.style.opacity = '0';
      setTimeout(() => tooltip.remove(), 200);
    }, 4000);
  }

  // ── Message listener ──

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'GET_PAPER_DATA') {
      // Re-detect in case DOM changed
      if (!detectedPaper) detectPaper();
      sendResponse({ paper: detectedPaper });
    }
    return false;
  });

  // ── Utilities ──

  function getMeta(name) {
    const el =
      document.querySelector(`meta[name="${name}"]`) ||
      document.querySelector(`meta[property="${name}"]`);
    return el ? el.getAttribute('content') : null;
  }

  function clean(str) {
    if (!str) return str;
    return str.replace(/\s+/g, ' ').trim();
  }

  /**
   * Last-resort heuristic: scan the page for a link that likely points to the paper's PDF.
   * Only called when citation_pdf_url and site-specific extractors found nothing.
   */
  function scanForPdfLink() {
    const EXCLUDED_URL = /\/(terms|privacy|policy|license|cookie|consent|guide|instructions|template|submission)\b/i;
    const PAYWALL = /[?&/](login|signin|authenticate|sso|cas|gateway|redirect|returnUrl|ticket)[=&/]/i;
    const EXCLUDED_CONTAINER = 'footer, nav, [role="navigation"], [role="contentinfo"]';
    const EXCLUDED_CLASS_ID = /(sidebar|cookie|footer|\bnav\b|menu|banner|\bad\b)/i;
    const NON_PRIMARY_TEXT = /\b(supplementar|appendix|supporting\s+info|reviewer|editorial|table\s+of\s+contents|errat)/i;
    const MAIN_CONTENT = 'main, article, [role="main"]';
    const MAIN_CONTENT_CLASS = /(content|paper|abstract|article|detail)/i;

    function isInMainContent(el) {
      if (el.closest(MAIN_CONTENT)) return true;
      let ancestor = el.parentElement;
      for (let i = 0; i < 6 && ancestor && ancestor !== document.body; i++) {
        if (MAIN_CONTENT_CLASS.test(ancestor.id || '') || MAIN_CONTENT_CLASS.test(ancestor.className || '')) return true;
        ancestor = ancestor.parentElement;
      }
      return false;
    }

    const links = document.querySelectorAll('a[href]');
    let best = null;
    let bestInMain = false;

    for (const link of links) {
      const href = link.href;
      if (!href || href.startsWith('javascript:') || href.startsWith('#')) continue;

      // Check if URL looks like a PDF
      let isPdfUrl = false;
      try {
        const url = new URL(href);
        const path = url.pathname.toLowerCase();
        isPdfUrl = path.endsWith('.pdf') || /\/pdf\//.test(path) ||
          /[?&](format|type)=pdf/i.test(url.search);
      } catch { continue; }

      // If URL doesn't look like PDF, check link text
      if (!isPdfUrl) {
        const text = (link.textContent || '').trim();
        const label = link.getAttribute('aria-label') || link.getAttribute('title') || '';
        if (!/\bpdf\b/i.test(text + ' ' + label)) continue;
      }

      // Exclusion filters
      try {
        const url = new URL(href);
        if (EXCLUDED_URL.test(url.pathname)) continue;
        if (PAYWALL.test(href)) continue;
      } catch { continue; }

      if (link.closest(EXCLUDED_CONTAINER)) continue;

      // Check ancestor classes/IDs
      let excluded = false;
      let ancestor = link.parentElement;
      for (let i = 0; i < 6 && ancestor && ancestor !== document.body; i++) {
        if (EXCLUDED_CLASS_ID.test(ancestor.id || '') || EXCLUDED_CLASS_ID.test(ancestor.className || '')) {
          excluded = true;
          break;
        }
        ancestor = ancestor.parentElement;
      }
      if (excluded) continue;

      if (NON_PRIMARY_TEXT.test((link.textContent || '').trim())) continue;

      const inMain = isInMainContent(link);
      if (!best || (inMain && !bestInMain)) {
        best = href;
        bestInMain = inMain;
        if (inMain) break;
      }
    }

    return best;
  }

  // ── Run detection ──

  detectPaper();

  // SPA publishers (IEEE, ACM, Wiley, ScienceDirect) render meta tags after initial
  // page load via JS frameworks. Re-run detection after a delay so we pick them up.
  const SPA_HOSTS = ['ieee.org', 'acm.org', 'wiley.com', 'sciencedirect.com'];
  const host = location.hostname;
  if (SPA_HOSTS.some((h) => host.includes(h))) {
    setTimeout(() => {
      const before = detectedPaper;
      detectPaper();
      // If we found more data on retry, notify popup if it's open
      if (detectedPaper && (!before || !before.authors || before.authors.length === 0) && detectedPaper.authors && detectedPaper.authors.length > 0) {
        showBadge();
      }
    }, 2500);
  }
})();
