"""
Tests for utility functions including domain validation and SSRF protection.
"""

import pytest
from django.test import override_settings

from image_url_upload.utils import (
    get_domain_from_url,
    is_domain_allowed,
    is_private_ip,
    validate_url_security,
)


class TestGetDomainFromUrl:
    """Test domain extraction from URLs."""

    def test_simple_domain(self):
        """Test extracting domain from simple URL."""
        assert get_domain_from_url("https://example.com/image.jpg") == "example.com"

    def test_subdomain(self):
        """Test extracting subdomain."""
        assert get_domain_from_url("https://cdn.example.com/image.jpg") == "cdn.example.com"

    def test_with_port(self):
        """Test domain with port number."""
        assert get_domain_from_url("https://example.com:8080/image.jpg") == "example.com:8080"

    def test_with_query_params(self):
        """Test domain extraction ignores query params."""
        assert get_domain_from_url("https://example.com/image.jpg?size=large") == "example.com"

    def test_case_insensitive(self):
        """Test domain is returned in lowercase."""
        assert get_domain_from_url("https://EXAMPLE.COM/image.jpg") == "example.com"

    def test_invalid_url(self):
        """Test handling of invalid URL."""
        assert get_domain_from_url("not a url") is ''

    def test_non_str_param(self):
        """Test handling of non str param."""
        assert get_domain_from_url(12345) is None


class TestIsDomainAllowed:
    """Test domain allow/block list functionality."""

    @override_settings(WAGTAIL_IMAGE_URL_ALLOWED_DOMAINS=['example.com', 'trusted.com'])
    def test_allowed_domain(self):
        """Test domain in allowed list."""
        is_allowed, error = is_domain_allowed("https://example.com/image.jpg")
        assert is_allowed is True
        assert error is None

    @override_settings(WAGTAIL_IMAGE_URL_ALLOWED_DOMAINS=['example.com', 'trusted.com'])
    def test_not_in_allowed_list(self):
        """Test domain not in allowed list."""
        is_allowed, error = is_domain_allowed("https://forbidden.com/image.jpg")
        assert is_allowed is False
        assert "not in the allowed domains list" in str(error)

    @override_settings(WAGTAIL_IMAGE_URL_BLOCKED_DOMAINS=['spam.com', 'malicious.com'])
    def test_blocked_domain(self):
        """Test domain in blocked list."""
        is_allowed, error = is_domain_allowed("https://spam.com/image.jpg")
        assert is_allowed is False
        assert "is blocked" in str(error)

    @override_settings(WAGTAIL_IMAGE_URL_BLOCKED_DOMAINS=['spam.com', 'malicious.com'])
    def test_not_in_blocked_list(self):
        """Test domain not in blocked list."""
        is_allowed, error = is_domain_allowed("https://example.com/image.jpg")
        assert is_allowed is True
        assert error is None

    @override_settings(
        WAGTAIL_IMAGE_URL_ALLOWED_DOMAINS=['example.com'],
        WAGTAIL_IMAGE_URL_BLOCKED_DOMAINS=['example.com']
    )
    def test_allowed_takes_precedence(self):
        """Test that allowed list takes precedence over blocked list."""
        is_allowed, error = is_domain_allowed("https://example.com/image.jpg")
        assert is_allowed is True
        assert error is None

    def test_no_restrictions(self):
        """Test when no allow/block lists are set."""
        is_allowed, error = is_domain_allowed("https://any-domain.com/image.jpg")
        assert is_allowed is True
        assert error is None

    @override_settings(WAGTAIL_IMAGE_URL_ALLOWED_DOMAINS=['EXAMPLE.COM'])
    def test_case_insensitive_allowed(self):
        """Test case insensitive domain matching in allowed list."""
        is_allowed, error = is_domain_allowed("https://example.com/image.jpg")
        assert is_allowed is True
        assert error is None

    @override_settings(WAGTAIL_IMAGE_URL_BLOCKED_DOMAINS=['SPAM.COM'])
    def test_case_insensitive_blocked(self):
        """Test case insensitive domain matching in blocked list."""
        is_allowed, error = is_domain_allowed("https://spam.com/image.jpg")
        assert is_allowed is False


class TestIsPrivateIp:
    """Test SSRF protection for private IP addresses."""

    def test_private_ipv4(self):
        """Test detection of private IPv4 addresses."""
        assert is_private_ip("http://192.168.1.1/image.jpg") is True
        assert is_private_ip("http://10.0.0.1/image.jpg") is True
        assert is_private_ip("http://172.16.0.1/image.jpg") is True

    def test_loopback(self):
        """Test detection of loopback addresses."""
        assert is_private_ip("http://127.0.0.1/image.jpg") is True
        assert is_private_ip("http://localhost/image.jpg") is True

    def test_public_ip(self):
        """Test that public IPs are not flagged as private."""
        assert is_private_ip("http://8.8.8.8/image.jpg") is False
        assert is_private_ip("http://1.1.1.1/image.jpg") is False

    def test_public_domain(self):
        """Test that public domains are not flagged as private."""
        assert is_private_ip("https://example.com/image.jpg") is False
        assert is_private_ip("https://google.com/image.jpg") is False

    def test_link_local(self):
        """Test detection of link-local addresses."""
        assert is_private_ip("http://169.254.1.1/image.jpg") is True


class TestValidateUrlSecurity:
    """Test comprehensive URL security validation."""

    @override_settings(WAGTAIL_IMAGE_URL_PREVENT_SSRF=True)
    def test_blocks_private_ip_when_enabled(self):
        """Test that private IPs are blocked when SSRF protection is enabled."""
        is_valid, error = validate_url_security("http://192.168.1.1/image.jpg")
        assert is_valid is False
        assert "private IP" in str(error)

    @override_settings(WAGTAIL_IMAGE_URL_PREVENT_SSRF=False)
    def test_allows_private_ip_when_disabled(self):
        """Test that private IPs are allowed when SSRF protection is disabled."""
        is_valid, error = validate_url_security("http://192.168.1.1/image.jpg")
        assert is_valid is True
        assert error is None

    @override_settings(
        WAGTAIL_IMAGE_URL_PREVENT_SSRF=True,
        WAGTAIL_IMAGE_URL_ALLOWED_DOMAINS=['example.com']
    )
    def test_checks_both_ssrf_and_domain(self):
        """Test that both SSRF and domain checks are performed."""
        # Should pass both checks
        is_valid, error = validate_url_security("https://example.com/image.jpg")
        assert is_valid is True
        assert error is None

        # Should fail domain check
        is_valid, error = validate_url_security("https://other.com/image.jpg")
        assert is_valid is False
        assert "not in the allowed domains list" in str(error)

        # Should fail SSRF check
        is_valid, error = validate_url_security("http://127.0.0.1/image.jpg")
        assert is_valid is False
        assert "private IP" in str(error)

    def test_default_ssrf_enabled(self):
        """Test that SSRF protection is enabled by default."""
        is_valid, error = validate_url_security("http://localhost/image.jpg")
        assert is_valid is False
        assert "private IP" in str(error)
