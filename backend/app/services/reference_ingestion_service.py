"""Utilities for ingesting reference PDFs into the document pipeline."""

from __future__ import annotations

import asyncio
import io
import ipaddress
import logging
import re
import socket
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.document_chunk import DocumentChunk
from app.models.reference import Reference
from app.models.research_paper import ResearchPaper
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

# ============================================================================
# SSRF Protection: Secure PDF Fetching
# ============================================================================
# This module fetches PDFs from untrusted URLs. To prevent SSRF attacks:
# 1. Block private/internal IP ranges (IPv4 + IPv6)
# 2. Manually follow redirects with validation at each hop
# 3. Resolve DNS once per hop to prevent DNS rebinding
# 4. Enforce size limits while streaming
# ============================================================================

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = 30

# Private/internal IP ranges to block
BLOCKED_IPV4_NETWORKS = [
    ipaddress.ip_network('10.0.0.0/8'),        # Private
    ipaddress.ip_network('172.16.0.0/12'),     # Private
    ipaddress.ip_network('192.168.0.0/16'),    # Private
    ipaddress.ip_network('127.0.0.0/8'),       # Loopback
    ipaddress.ip_network('169.254.0.0/16'),    # Link-local / cloud metadata
    ipaddress.ip_network('0.0.0.0/8'),         # "This" network
    ipaddress.ip_network('100.64.0.0/10'),     # Carrier-grade NAT
    ipaddress.ip_network('192.0.0.0/24'),      # IETF protocol assignments
    ipaddress.ip_network('192.0.2.0/24'),      # TEST-NET-1
    ipaddress.ip_network('198.51.100.0/24'),   # TEST-NET-2
    ipaddress.ip_network('203.0.113.0/24'),    # TEST-NET-3
    ipaddress.ip_network('224.0.0.0/4'),       # Multicast
    ipaddress.ip_network('240.0.0.0/4'),       # Reserved
]

BLOCKED_IPV6_NETWORKS = [
    ipaddress.ip_network('::1/128'),           # Loopback
    ipaddress.ip_network('fc00::/7'),          # Unique local
    ipaddress.ip_network('fe80::/10'),         # Link-local
    ipaddress.ip_network('ff00::/8'),          # Multicast
    ipaddress.ip_network('::ffff:0:0/96'),     # IPv4-mapped (check underlying IPv4)
]


class SSRFError(Exception):
    """Raised when a URL fails SSRF validation."""
    pass


def _make_ip_pinned_request(
    url: str,
    resolved_ip: str,
    hostname: str,
    headers: dict,
    timeout: int,
) -> requests.Response:
    """Make a request pinned to a specific IP address.

    This prevents DNS rebinding by connecting to the resolved IP
    while preserving the original hostname for Host header and TLS SNI.

    For HTTPS: Uses server_hostname for proper SNI and cert validation.
    For HTTP: Simply connects to the IP with Host header.
    """
    import ssl
    import urllib3

    parsed = urlparse(url)

    # Build URL with IP instead of hostname
    port = parsed.port
    port_str = f":{port}" if port else ""

    ip_obj = ipaddress.ip_address(resolved_ip)
    ip_host = f"[{resolved_ip}]" if isinstance(ip_obj, ipaddress.IPv6Address) else resolved_ip

    path = parsed.path or "/"
    ip_url = f"{parsed.scheme}://{ip_host}{port_str}{path}"
    if parsed.query:
        ip_url += f"?{parsed.query}"

    # Set Host header to original hostname (required for virtual hosts)
    request_headers = headers.copy()
    if port and ((parsed.scheme == 'https' and port != 443) or (parsed.scheme == 'http' and port != 80)):
        request_headers['Host'] = f"{hostname}:{port}"
    else:
        request_headers['Host'] = hostname

    if parsed.scheme == 'https':
        # For HTTPS, we need to:
        # 1. Connect to the resolved IP
        # 2. Use original hostname for SNI (server_hostname in SSL context)
        # 3. Verify certificate against original hostname

        # Create SSL context with proper server_hostname
        ctx = ssl.create_default_context()

        # Use urllib3 directly for fine-grained control
        http = urllib3.HTTPSConnectionPool(
            resolved_ip,
            port=port or 443,
            cert_reqs='CERT_REQUIRED',
            ca_certs=None,  # Use system CA
            ssl_context=ctx,
            server_hostname=hostname,  # Critical: SNI and cert validation
            assert_hostname=hostname,
            timeout=urllib3.Timeout(connect=timeout, read=timeout),
        )

        try:
            request_path = path + (f"?{parsed.query}" if parsed.query else "")
            response = http.request(
                'GET',
                request_path,
                headers=request_headers,
                preload_content=False,  # Enable streaming
                redirect=False,
            )

            # Wrap in requests.Response for consistent interface
            resp = requests.Response()
            resp.status_code = response.status
            resp.headers = requests.structures.CaseInsensitiveDict(response.headers)
            resp.raw = response
            resp._content_consumed = False
            resp.request = requests.Request('GET', url, headers=request_headers).prepare()

            return resp
        except Exception as e:
            logger.debug("HTTPS request to %s failed: %s", resolved_ip, e)
            raise requests.RequestException(f"HTTPS request failed: {e}")
    else:
        # For HTTP, simple request with Host header is sufficient
        return requests.get(
            ip_url,
            headers=request_headers,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )


def _is_ip_blocked(ip_str: str) -> bool:
    """Check if an IP address is in a blocked range."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # Invalid IP = blocked

    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in BLOCKED_IPV4_NETWORKS)
    elif isinstance(ip, ipaddress.IPv6Address):
        # Check IPv6 ranges
        if any(ip in net for net in BLOCKED_IPV6_NETWORKS):
            return True
        # For IPv4-mapped IPv6 addresses, also check IPv4 ranges
        if ip.ipv4_mapped:
            return any(ip.ipv4_mapped in net for net in BLOCKED_IPV4_NETWORKS)
        return False
    return True  # Unknown type = blocked


def _resolve_and_validate_host(hostname: str) -> str:
    """Resolve hostname to IP and validate it's not blocked.

    Returns the resolved IP address if safe.
    Raises SSRFError if the host resolves to a blocked IP.
    """
    try:
        # Get all address info (supports both IPv4 and IPv6)
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not addr_info:
            raise SSRFError(f"Could not resolve hostname: {hostname}")

        # Check all resolved IPs - if any is blocked, reject
        resolved_ips = set()
        for _, _, _, _, sockaddr in addr_info:
            ip = str(sockaddr[0])
            resolved_ips.add(ip)
            if _is_ip_blocked(ip):
                raise SSRFError(f"Blocked IP address: {ip} (from {hostname})")

        # Return first resolved IP for connection
        return str(addr_info[0][4][0])
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for {hostname}: {e}")


def _validate_url_scheme(url: str) -> None:
    """Ensure URL uses HTTPS or HTTP scheme."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise SSRFError(f"Invalid URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise SSRFError(f"No hostname in URL: {url}")


def _fetch_pdf_secure(url: str) -> Optional[Tuple[bytes, str]]:
    """Securely fetch a PDF with SSRF protection.

    Returns (content_bytes, final_url) or None on failure.

    Security measures:
    - Validates URL scheme (http/https only)
    - Resolves DNS once and pins connection to that IP (prevents DNS rebinding)
    - Manually follows redirects with validation at each hop
    - Streams response to BytesIO with size limit (prevents memory spikes)
    - Validates content type
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,*/*",
    }

    current_url = url

    for redirect_count in range(MAX_REDIRECTS + 1):
        try:
            # Validate URL scheme
            _validate_url_scheme(current_url)
            parsed = urlparse(current_url)
            hostname = parsed.hostname
            if not hostname:
                # Should not happen - _validate_url_scheme checks this
                raise SSRFError(f"No hostname in URL: {current_url}")

            # Resolve DNS and validate IP before connecting
            resolved_ip = _resolve_and_validate_host(hostname)
            logger.debug("Resolved %s to %s (pinning connection)", hostname, resolved_ip)

            # Make IP-pinned request (prevents DNS rebinding)
            resp = _make_ip_pinned_request(
                url=current_url,
                resolved_ip=resolved_ip,
                hostname=hostname,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

            # Handle redirects manually
            if resp.status_code in (301, 302, 303, 307, 308):
                if redirect_count >= MAX_REDIRECTS:
                    logger.warning("Too many redirects for %s", url)
                    return None

                location = resp.headers.get('Location')
                if not location:
                    logger.warning("Redirect without Location header from %s", current_url)
                    return None

                # Resolve relative redirects
                current_url = urljoin(current_url, location)
                logger.debug("Following redirect to %s", current_url)
                resp.close()
                continue

            if resp.status_code != 200:
                logger.info("PDF download from %s returned status %s", current_url, resp.status_code)
                resp.close()
                return None

            # Validate content type
            content_type = (resp.headers.get("content-type") or "").lower()
            is_pdf_content = "pdf" in content_type or "octet-stream" in content_type
            is_pdf_url = current_url.lower().endswith(".pdf") or "download" in current_url.lower()

            if not is_pdf_content and not is_pdf_url:
                logger.info("Content from %s is not a PDF (content-type=%s)", current_url, content_type)
                resp.close()
                return None

            # Stream to BytesIO with size limit (avoids memory spike from list + join)
            buffer = io.BytesIO()
            total_size = 0

            for chunk in resp.iter_content(chunk_size=8192):
                total_size += len(chunk)
                if total_size > MAX_PDF_SIZE:
                    logger.warning("PDF from %s exceeds size limit (%d bytes)", url, MAX_PDF_SIZE)
                    resp.close()
                    buffer.close()
                    return None
                buffer.write(chunk)

            resp.close()
            content = buffer.getvalue()
            buffer.close()

            if not content:
                logger.info("Downloaded PDF from %s is empty", current_url)
                return None

            return (content, current_url)

        except SSRFError as e:
            logger.warning("SSRF protection blocked %s: %s", current_url, e)
            return None
        except requests.RequestException as e:
            logger.warning("Failed to download PDF from %s: %s", current_url, e)
            return None
        except Exception as e:
            logger.warning("Unexpected error fetching PDF from %s: %s", current_url, e)
            return None

    logger.warning("Redirect loop detected for %s", url)
    return None


def _run_async(coro):
    """Execute an async coroutine from synchronous context.

    Uses a thread pool to properly handle running async code when
    an event loop is already running (e.g., from FastAPI).
    """
    import concurrent.futures

    def run_in_thread():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Run in a separate thread to avoid nested event loop issues
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result(timeout=60)

    return asyncio.run(coro)


def _sanitize_filename(title: Optional[str]) -> str:
    base = title or "reference"
    base = base.strip().lower()[:96]
    base = re.sub(r"[^a-z0-9_-]+", "-", base)
    base = base.strip("-") or "reference"
    return f"{base}.pdf"


def _resolve_owner_id(db: Session, reference: Reference, fallback_owner: Optional[str] = None) -> str:
    if reference.paper_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == reference.paper_id).first()
        if paper and paper.owner_id:
            return str(paper.owner_id)
    if reference.owner_id:
        return str(reference.owner_id)
    if fallback_owner:
        return str(fallback_owner)
    raise ValueError("Unable to resolve owner for reference document ingestion")


def _fetch_pdf(url: str) -> Optional[bytes]:
    """Fetch PDF with SSRF protection. Returns content bytes or None."""
    result = _fetch_pdf_secure(url)
    if result is None:
        return None
    return result[0]  # Return just the content bytes


def ingest_reference_pdf(
    db: Session,
    reference: Reference,
    *,
    owner_id: Optional[str] = None,
) -> bool:
    """Download a reference PDF, store it as a document, and chunk it for AI."""

    if not getattr(reference, "pdf_url", None):
        return False

    existing_document: Optional[Document] = None
    if getattr(reference, "document_id", None):
        existing_document = db.query(Document).filter(Document.id == reference.document_id).first()

    # If document already exists and is processed, ensure status reflects it
    if existing_document and existing_document.status == DocumentStatus.PROCESSED and existing_document.is_processed_for_ai:
        if reference.status != 'analyzed':
            reference.status = 'analyzed'
            try:
                db.commit()
            except Exception:
                db.rollback()
        return True

    ds = DocumentService()

    # Download PDF when no document is stored yet
    if not existing_document:
        base_url = reference.url or ""
        pdf_url = urljoin(base_url, reference.pdf_url)
        pdf_content = _fetch_pdf(pdf_url)
        if pdf_content is None:
            return False

        filename = _sanitize_filename(reference.title)

        try:
            file_path = _run_async(ds.save_uploaded_file(pdf_content, filename))
        except Exception as exc:
            logger.error("Unable to persist downloaded PDF for reference %s: %s", reference.id, exc)
            return False

        try:
            resolved_owner = _resolve_owner_id(db, reference, owner_id)
        except ValueError as exc:
            logger.warning("Skipping PDF ingestion for reference %s: %s", reference.id, exc)
            return False

        document = Document(
            filename=filename,
            original_filename=filename,
            file_path=file_path,
            file_size=len(pdf_content),
            mime_type="application/pdf",
            document_type=DocumentType.PDF,
            file_hash=ds.duplicate_detector.calculate_file_hash(pdf_content),
            title=reference.title,
            doi=reference.doi,
            journal=reference.journal,
            owner_id=resolved_owner,
            paper_id=reference.paper_id,
            status=DocumentStatus.PROCESSING,
        )

        # Use savepoint to avoid affecting outer transaction on failure
        try:
            with db.begin_nested():
                db.add(document)
            db.commit()
            db.refresh(document)
        except Exception as exc:
            db.rollback()
            logger.error("Failed to create document record for reference %s: %s", reference.id, exc)
            return False

        document_bytes = pdf_content
    else:
        document = existing_document
        try:
            with open(document.file_path, 'rb') as fh:
                document_bytes = fh.read()
        except Exception as exc:
            logger.error("Failed to read stored PDF for reference %s: %s", reference.id, exc)
            return False

    # Re-run document processing
    try:
        _run_async(ds.process_document(db, document, document_bytes, None))
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Document processing for reference %s failed: %s", reference.id, exc)

    # Link chunks to reference - use expire_all instead of rollback to preserve outer transaction
    try:
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).all()
        for chunk in chunks:
            chunk.reference_id = reference.id
        if chunks:
            db.commit()
    except Exception as exc:  # pragma: no cover - chunk linking best effort
        db.expire_all()  # Clear stale state without affecting committed data
        logger.warning("Failed linking chunks to reference %s: %s", reference.id, exc)

    # Update reference status
    reference.document_id = document.id
    reference.status = 'analyzed'
    try:
        db.commit()
    except Exception as exc:
        db.expire_all()  # Clear stale state without affecting committed data
        logger.warning("Failed to persist reference %s after PDF ingestion: %s", reference.id, exc)
        return False

    logger.info("Ingested or refreshed PDF for reference %s", reference.id)
    return True
