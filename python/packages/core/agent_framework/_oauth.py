# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger("agent_framework")

__all__ = ["validate_oauth_consent_link"]

# Characters allowed in a registered host name, and in the bracketed IPv6 form that
# ``urlparse`` reports with its brackets already stripped.
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9._~%-]+$")
_IPV6_HOST_PATTERN = re.compile(r"^[0-9A-Fa-f:.%-]+$")


def _is_valid_host(hostname: str) -> bool:
    """Return whether *hostname* is syntactically usable by a standard URL client.

    ``urlparse`` does not reject hosts containing illegal characters, so values such as
    ``exa mple.com`` are reported as a hostname even though no client can resolve them.
    """
    pattern = _IPV6_HOST_PATTERN if ":" in hostname else _HOST_PATTERN
    return bool(pattern.match(hostname))


def validate_oauth_consent_link(consent_link: str | None, *, item_id: str | None = None) -> str | None:
    """Return *consent_link* when it is an absolute HTTPS URL a client can open, else ``None``.

    A consent link is rendered as a clickable prompt by the client, so anything that is not
    an absolute ``https`` URL is dropped rather than surfaced. Validation is shared by every
    package that parses or re-emits ``oauth_consent_request`` content so the accepted shape
    cannot drift between the provider that parses a link and the host that renders it.

    ``urlparse`` is permissive in three ways that matter here, all handled below:

    * it raises ``ValueError`` for malformed authorities (``https://[broken``) and for invalid
      ports, but the port is only validated when it is read;
    * a non-empty ``netloc`` does not imply a host (``https://@`` has one but no host), and a
      non-empty ``hostname`` does not imply a usable one (``https://exa mple.com`` reports one);
    * it silently strips tab and newline, so control characters must be rejected up front.

    Args:
        consent_link: The candidate consent URL, which may be ``None`` or empty.

    Keyword Args:
        item_id: Optional identifier of the source item, included in warning logs.

    Returns:
        The link unchanged when it is usable, otherwise ``None``.
    """
    if not consent_link:
        return None

    log_id = item_id or "<unknown>"

    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in consent_link):
        logger.warning(
            "Skipping oauth_consent_request with whitespace or control characters in consent_link (item id=%s)",
            log_id,
        )
        return None
    try:
        parsed = urlparse(consent_link)
        hostname = parsed.hostname
        # Reading ``port`` is what validates it; ``https://host:bad`` raises here.
        _ = parsed.port
    except ValueError:
        logger.warning("Skipping oauth_consent_request with malformed consent_link (item id=%s)", log_id)
        return None
    if parsed.scheme.lower() != "https" or not hostname:
        logger.warning("Skipping oauth_consent_request with non-HTTPS consent_link (item id=%s)", log_id)
        return None
    if not _is_valid_host(hostname):
        logger.warning("Skipping oauth_consent_request with an invalid consent_link host (item id=%s)", log_id)
        return None
    return consent_link
