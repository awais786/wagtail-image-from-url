"""
Utility functions for image URL upload.
"""

import ipaddress
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def get_domain_from_url(url):
    """
    Extract domain from URL.

    Args:
        url: The URL to parse

    Returns:
        str: The domain (e.g., 'example.com')
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception as e:
        logger.warning(f"Failed to parse URL {url}: {e}")
        return None


def is_domain_allowed(url):
    """
    Check if a domain is allowed based on allow/block lists.

    Args:
        url: The URL to check

    Returns:
        tuple: (is_allowed: bool, error_message: str or None)
    """
    domain = get_domain_from_url(url)

    if not domain:
        return False, _("Invalid URL format.")

    allowed_domains = getattr(settings, 'WAGTAIL_IMAGE_URL_ALLOWED_DOMAINS', None)
    if allowed_domains is not None:
        allowed_domains = {domain.lower() for domain in allowed_domains}
        if domain not in allowed_domains:
            logger.warning(f"Domain {domain} not in allowed list")
            return False, _("Domain '{domain}' is not in the allowed domains list.").format(domain=domain)
        return True, None

    blocked_domains = getattr(settings, 'WAGTAIL_IMAGE_URL_BLOCKED_DOMAINS', [])
    blocked_domains = {domain.lower() for domain in blocked_domains}
    if domain in blocked_domains:
        logger.warning(f"Domain {domain} is blocked")
        return False, _("Domain '{domain}' is blocked.").format(domain=domain)

    return True, None


def is_private_ip(url):
    """
    Check if URL points to a private/internal IP address.

    This helps prevent Server-Side Request Forgery (SSRF) attacks.

    Args:
        url: The URL to check

    Returns:
        bool: True if the URL appears to point to a private IP
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False

        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        except ValueError:
            # Not an IP address, it's a hostname
            # Check for localhost variations
            if hostname.lower() in ('localhost', '127.0.0.1', '::1'):
                return True
            return False
    except Exception as e:
        logger.warning(f"Error checking private IP for {url}: {e}")
        return False


def validate_url_security(url):
    """
    Comprehensive URL security validation.

    Args:
        url: The URL to validate

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    # Check if SSRF protection is enabled
    prevent_ssrf = getattr(settings, 'WAGTAIL_IMAGE_URL_PREVENT_SSRF', True)

    if prevent_ssrf and is_private_ip(url):
        logger.warning(f"Blocked private IP address: {url}")
        return False, _("URLs pointing to private IP addresses are not allowed.")

    # Check domain allow/block lists
    return is_domain_allowed(url)

