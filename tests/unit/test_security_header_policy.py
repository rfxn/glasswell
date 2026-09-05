"""The header policy itself, decided before any surface is asked for it.

`test_security_headers.py` asserts every served surface carries these; what is only asked here
is what the policy *is* — which needs neither an app nor a database, and so belongs in the tier
a docker-free run collects.
"""

from __future__ import annotations

from glasswell.api.security import (
    HSTS_HEADER,
    HSTS_POLICY,
    STATIC_SECURITY_HEADERS,
    content_security_policy,
    hsts_for,
)


def test_the_plain_http_origin_does_not_upgrade_its_own_subresources() -> None:
    """The LAN break-glass path is served over http; upgrading would break every request."""
    assert "upgrade-insecure-requests" not in content_security_policy(https=False)
    assert "upgrade-insecure-requests" in content_security_policy(https=True)


def test_hsts_carries_a_year_and_subdomains_and_never_preload() -> None:
    policy = hsts_for(https=True)

    assert policy == HSTS_POLICY
    assert "max-age=31536000" in policy
    assert "includeSubDomains" in policy
    # preload is effectively irreversible and commits every host under the zone.
    assert "preload" not in policy
    assert hsts_for(https=False) is None


def test_hsts_is_not_a_member_of_the_static_header_mapping() -> None:
    """test_caddy_basemap_headers.py parametrises over that mapping, so a member here would be
    demanded on the plain-http basemap path too."""
    assert HSTS_HEADER not in STATIC_SECURITY_HEADERS
