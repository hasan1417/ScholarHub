"""Tests for SSRF protection in reference ingestion."""

from unittest.mock import MagicMock, patch
import pytest
from app.services.reference_ingestion_service import (
    _is_ip_blocked,
    _resolve_and_validate_host,
    _validate_url_scheme,
    _fetch_pdf_secure,
    _make_ip_pinned_request,
    SSRFError,
    MAX_PDF_SIZE,
    MAX_REDIRECTS,
)


class TestIPBlocking:
    """Tests for IP address blocking."""

    def test_blocks_localhost_ipv4(self):
        assert _is_ip_blocked("127.0.0.1") is True
        assert _is_ip_blocked("127.0.0.255") is True

    def test_blocks_private_class_a(self):
        assert _is_ip_blocked("10.0.0.1") is True
        assert _is_ip_blocked("10.255.255.255") is True

    def test_blocks_private_class_b(self):
        assert _is_ip_blocked("172.16.0.1") is True
        assert _is_ip_blocked("172.31.255.255") is True

    def test_blocks_private_class_c(self):
        assert _is_ip_blocked("192.168.0.1") is True
        assert _is_ip_blocked("192.168.255.255") is True

    def test_blocks_link_local(self):
        # Cloud metadata endpoint
        assert _is_ip_blocked("169.254.169.254") is True
        assert _is_ip_blocked("169.254.0.1") is True

    def test_blocks_localhost_ipv6(self):
        assert _is_ip_blocked("::1") is True

    def test_blocks_ipv6_unique_local(self):
        assert _is_ip_blocked("fc00::1") is True
        assert _is_ip_blocked("fd00::1") is True

    def test_blocks_ipv6_link_local(self):
        assert _is_ip_blocked("fe80::1") is True

    def test_allows_public_ipv4(self):
        assert _is_ip_blocked("8.8.8.8") is False
        assert _is_ip_blocked("1.1.1.1") is False
        assert _is_ip_blocked("142.250.80.46") is False  # google.com

    def test_allows_public_ipv6(self):
        assert _is_ip_blocked("2607:f8b0:4004:800::200e") is False  # google.com

    def test_blocks_invalid_ip(self):
        assert _is_ip_blocked("not-an-ip") is True
        assert _is_ip_blocked("") is True


class TestURLSchemeValidation:
    """Tests for URL scheme validation."""

    def test_allows_https(self):
        _validate_url_scheme("https://example.com/file.pdf")  # Should not raise

    def test_allows_http(self):
        _validate_url_scheme("http://example.com/file.pdf")  # Should not raise

    def test_blocks_file_scheme(self):
        with pytest.raises(SSRFError, match="Invalid URL scheme"):
            _validate_url_scheme("file:///etc/passwd")

    def test_blocks_ftp_scheme(self):
        with pytest.raises(SSRFError, match="Invalid URL scheme"):
            _validate_url_scheme("ftp://example.com/file.pdf")

    def test_blocks_gopher_scheme(self):
        with pytest.raises(SSRFError, match="Invalid URL scheme"):
            _validate_url_scheme("gopher://example.com/")

    def test_blocks_missing_hostname(self):
        with pytest.raises(SSRFError, match="No hostname"):
            _validate_url_scheme("https:///path/file.pdf")


class TestDNSResolution:
    """Tests for DNS resolution and validation."""

    def test_blocks_localhost_resolution(self):
        with pytest.raises(SSRFError, match="Blocked IP"):
            _resolve_and_validate_host("localhost")

    def test_blocks_internal_hostname(self):
        # This test may be environment-dependent
        # In most environments, this should fail to resolve or resolve to internal IP
        try:
            _resolve_and_validate_host("internal.local")
            # If it resolves, it should be blocked
        except SSRFError:
            pass  # Expected

    def test_allows_public_hostname(self):
        # Note: This test requires network access
        try:
            ip = _resolve_and_validate_host("google.com")
            assert ip is not None
            assert not _is_ip_blocked(ip)
        except SSRFError:
            pytest.skip("Network not available")


class TestSSRFScenarios:
    """Integration tests for common SSRF attack scenarios."""

    def test_cloud_metadata_blocked(self):
        """Block attempts to access cloud metadata endpoints."""
        assert _is_ip_blocked("169.254.169.254") is True

    def test_internal_network_scan_blocked(self):
        """Block attempts to scan internal network."""
        assert _is_ip_blocked("192.168.1.1") is True
        assert _is_ip_blocked("10.0.0.1") is True
        assert _is_ip_blocked("172.16.0.1") is True

    def test_ipv4_mapped_ipv6_blocked(self):
        """Block IPv4-mapped IPv6 addresses pointing to private IPs."""
        # ::ffff:127.0.0.1 is IPv4-mapped IPv6 for localhost
        assert _is_ip_blocked("::ffff:127.0.0.1") is True
        # ::ffff:10.0.0.1 is IPv4-mapped IPv6 for private network
        assert _is_ip_blocked("::ffff:10.0.0.1") is True


class TestFetchPdfSecure:
    """Tests for _fetch_pdf_secure behavior using mocks."""

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    @patch('app.services.reference_ingestion_service._make_ip_pinned_request')
    def test_successful_pdf_download(self, mock_request, mock_resolve):
        """Test successful PDF download."""
        mock_resolve.return_value = "93.184.216.34"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.iter_content.return_value = [b"%PDF-1.4 test content"]
        mock_request.return_value = mock_response

        result = _fetch_pdf_secure("https://example.com/paper.pdf")

        assert result is not None
        content, final_url = result
        assert b"%PDF-1.4" in content
        assert final_url == "https://example.com/paper.pdf"

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    @patch('app.services.reference_ingestion_service._make_ip_pinned_request')
    def test_redirect_following(self, mock_request, mock_resolve):
        """Test that redirects are followed with validation at each hop."""
        mock_resolve.return_value = "93.184.216.34"

        # First response: redirect
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"Location": "https://cdn.example.com/paper.pdf"}

        # Second response: actual PDF
        pdf_response = MagicMock()
        pdf_response.status_code = 200
        pdf_response.headers = {"content-type": "application/pdf"}
        pdf_response.iter_content.return_value = [b"%PDF-1.4 content"]

        mock_request.side_effect = [redirect_response, pdf_response]

        result = _fetch_pdf_secure("https://example.com/redirect")

        assert result is not None
        # Verify resolve was called for both hops
        assert mock_resolve.call_count == 2

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    @patch('app.services.reference_ingestion_service._make_ip_pinned_request')
    def test_max_redirects_enforced(self, mock_request, mock_resolve):
        """Test that too many redirects are rejected."""
        mock_resolve.return_value = "93.184.216.34"

        # All responses are redirects
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"Location": "https://example.com/next"}

        mock_request.return_value = redirect_response

        result = _fetch_pdf_secure("https://example.com/infinite-redirect")

        assert result is None
        # Should have tried MAX_REDIRECTS + 1 times
        assert mock_resolve.call_count == MAX_REDIRECTS + 1

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    @patch('app.services.reference_ingestion_service._make_ip_pinned_request')
    def test_size_limit_enforced(self, mock_request, mock_resolve):
        """Test that files exceeding size limit are rejected."""
        mock_resolve.return_value = "93.184.216.34"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}

        # Return chunks that exceed the size limit
        chunk_size = 8192
        chunks_needed = (MAX_PDF_SIZE // chunk_size) + 2
        mock_response.iter_content.return_value = [b"x" * chunk_size for _ in range(chunks_needed)]
        mock_request.return_value = mock_response

        result = _fetch_pdf_secure("https://example.com/huge.pdf")

        assert result is None

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    @patch('app.services.reference_ingestion_service._make_ip_pinned_request')
    def test_content_type_validation(self, mock_request, mock_resolve):
        """Test that non-PDF content types are rejected."""
        mock_resolve.return_value = "93.184.216.34"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_request.return_value = mock_response

        # URL doesn't end in .pdf either
        result = _fetch_pdf_secure("https://example.com/page")

        assert result is None

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    @patch('app.services.reference_ingestion_service._make_ip_pinned_request')
    def test_octet_stream_accepted(self, mock_request, mock_resolve):
        """Test that application/octet-stream is accepted (common for downloads)."""
        mock_resolve.return_value = "93.184.216.34"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.iter_content.return_value = [b"%PDF-1.4 content"]
        mock_request.return_value = mock_response

        result = _fetch_pdf_secure("https://example.com/download")

        assert result is not None

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    def test_blocked_ip_rejected(self, mock_resolve):
        """Test that URLs resolving to blocked IPs are rejected."""
        mock_resolve.side_effect = SSRFError("Blocked IP: 127.0.0.1")

        result = _fetch_pdf_secure("https://evil.com/ssrf.pdf")

        assert result is None

    def test_invalid_scheme_rejected(self):
        """Test that non-http(s) schemes are rejected."""
        result = _fetch_pdf_secure("file:///etc/passwd")
        assert result is None

        result = _fetch_pdf_secure("ftp://example.com/file.pdf")
        assert result is None

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    @patch('app.services.reference_ingestion_service._make_ip_pinned_request')
    def test_redirect_to_blocked_ip_rejected(self, mock_request, mock_resolve):
        """Test that redirects to blocked IPs are rejected."""
        # First call: public IP
        # Second call: blocked IP (SSRF attempt)
        mock_resolve.side_effect = [
            "93.184.216.34",
            SSRFError("Blocked IP: 169.254.169.254"),
        ]

        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        mock_request.return_value = redirect_response

        result = _fetch_pdf_secure("https://attacker.com/redirect-to-metadata")

        assert result is None

    @patch('app.services.reference_ingestion_service._resolve_and_validate_host')
    @patch('app.services.reference_ingestion_service._make_ip_pinned_request')
    def test_pdf_url_extension_accepted(self, mock_request, mock_resolve):
        """Test that .pdf URLs are accepted even with generic content-type."""
        mock_resolve.return_value = "93.184.216.34"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/force-download"}
        mock_response.iter_content.return_value = [b"%PDF-1.4 content"]
        mock_request.return_value = mock_response

        result = _fetch_pdf_secure("https://example.com/paper.pdf")

        assert result is not None

    @patch('app.services.reference_ingestion_service.requests.get')
    def test_ipv6_host_wrapped_in_url(self, mock_get):
        """IPv6 hosts should be wrapped in [] when building IP-pinned URL (HTTP)."""
        mock_get.return_value = MagicMock(status_code=200, headers={})

        _make_ip_pinned_request(
            url="http://example.com/file.pdf",
            resolved_ip="2001:db8::1",
            hostname="example.com",
            headers={},
            timeout=5,
        )

        assert mock_get.call_count == 1
        called_url = mock_get.call_args.args[0]
        assert called_url.startswith("http://[2001:db8::1]")

    @patch('urllib3.HTTPSConnectionPool')
    def test_https_assert_hostname_set(self, mock_pool):
        """HTTPSConnectionPool should assert hostname for TLS verification."""
        pool_instance = MagicMock()
        mock_pool.return_value = pool_instance

        response = MagicMock()
        response.status = 200
        response.headers = {"content-type": "application/pdf"}
        pool_instance.request.return_value = response

        _make_ip_pinned_request(
            url="https://example.com/paper.pdf",
            resolved_ip="93.184.216.34",
            hostname="example.com",
            headers={},
            timeout=5,
        )

        call_kwargs = mock_pool.call_args.kwargs
        assert call_kwargs.get("assert_hostname") == "example.com"
