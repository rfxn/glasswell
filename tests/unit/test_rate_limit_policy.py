"""The rate-limit policy: the bucket table, the class each principal falls in, the refusal.

Every assertion here reads a constant, a pure function or a module's own source, so none of it
needs the counter -- and the counter, the grants on its table and the atomicity of the window
are asserted against a real database in tests/integration/test_api_rate_limit.py.
"""

from __future__ import annotations

import pytest

from glasswell.api.principal import Principal


def test_the_bucket_table_carries_the_ruled_limits_and_the_stated_additions() -> None:
    """Policy as data. The four ruled buckets are exact; the three additions are named here
    so adding a fourth cannot pass unnoticed, each with the reason it exists."""
    from glasswell.api.rate_limit import BUCKETS

    ruled = {"interactive": 120, "service": 60, "tiles": 600, "anonymous": 30}
    assert {name: BUCKETS[name] for name in ruled} == ruled

    # deploy: verify.sh + smoke.sh are 64 requests back to back and would self-throttle.
    # login/challenge: the two open session routes run before a principal exists, so the
    # resolved address is the only key available.
    # admin_write: the two owner routes that hash a password, kept off login's budget.
    assert set(BUCKETS) - set(ruled) == {"deploy", "login", "challenge", "admin_write"}


@pytest.mark.parametrize(
    ("kind", "scope", "path", "expected"),
    [
        ("user", "owner", "/v1/wells", "interactive"),
        ("user", "guest", "/v1/glossary", "interactive"),
        ("owner", "owner", "/v1/wells", "deploy"),
        ("service", "guest", "/v1/wells", "service"),
        ("anonymous", "guest", "/v1/wells", "anonymous"),
        ("user", "owner", "/v1/tiles/nd_wells/8/54/89.pbf", "tiles"),
        # An anonymous caller has no principal to key on, so even on a tile path the
        # address is the bucket -- otherwise every anonymous tile request in the world
        # shares one counter named for the class.
        ("anonymous", "guest", "/v1/tiles/nd_wells/8/54/89.pbf", "anonymous"),
    ],
)
def test_each_principal_class_falls_in_its_ruled_bucket(kind, scope, path, expected) -> None:
    from glasswell.api.rate_limit import bucket_for

    principal = Principal(id="probe", kind=kind, scope=scope)

    assert bucket_for(principal, path)[0] == expected


def test_the_password_hashing_routes_are_bounded_before_they_hash() -> None:
    """POST /v1/users and POST /v1/users/{id}/password both run Argon2id at 64 MiB. The bucket
    is charged as the handler's first statement, so a caller cannot buy the work by being
    refused later in the route."""
    import inspect

    from glasswell.api.rate_limit import BUCKETS
    from glasswell.api.routers.users import create_user, set_user_password

    assert BUCKETS["admin_write"] == BUCKETS["login"]
    for handler in (create_user, set_user_password):
        body = [
            line.strip()
            for line in inspect.getsource(handler).splitlines()
            if line.strip() and not line.strip().startswith(("#", '"""'))
        ]
        charged = next(index for index, line in enumerate(body) if "consume_login_bucket" in line)
        hashed = next(
            (index for index, line in enumerate(body) if "password=" in line), len(body)
        )
        assert charged < hashed, f"{handler.__name__} hashes before it charges"


def test_the_deploy_credential_is_bounded_not_exempt() -> None:
    """deploy.sh runs verify.sh (33 requests) and smoke.sh (31) back to back, so the gate
    exceeds the 60/min service bucket by itself. The static owner key gets its own ceiling
    -- reachable only off the tunnel, and still a ceiling."""
    from glasswell.api.rate_limit import BUCKETS

    assert BUCKETS["deploy"] > 64, "the deploy gate would throttle itself"
    assert BUCKETS["deploy"] < 10_000, "a bucket this large is an exemption, not a limit"


def test_an_issued_key_does_not_get_the_deploy_ceiling() -> None:
    """Only the static owner key. An issued key is kind=service and stays at 60/min."""
    from glasswell.api.rate_limit import bucket_for

    issued = Principal(id="key:key_1", kind="service", scope="owner")

    assert bucket_for(issued, "/v1/wells")[0] == "service"


def test_the_refusal_does_not_name_which_bucket_fired() -> None:
    from glasswell.api.rate_limit import BUCKETS, _uniform_refusal

    refusal = _uniform_refusal()

    assert refusal.code == "rate_limited"
    for name in BUCKETS:
        assert name not in (refusal.detail or "")


def test_retry_after_is_rounded_to_thirty_seconds() -> None:
    from glasswell.api.rate_limit import RETRY_AFTER_GRANULARITY, _uniform_refusal

    retry = int(_uniform_refusal().headers["Retry-After"])

    assert retry % RETRY_AFTER_GRANULARITY == 0
    assert retry > 0


def test_the_unmet_concurrency_caps_are_recorded_in_the_module() -> None:
    """§3.6.8's 32 global concurrency and 5 concurrent jobs cannot be expressed by a fixed
    window. Recorded as unmet rather than asserted by a test that measures nothing."""
    import glasswell.api.rate_limit as module

    assert "concurren" in (module.__doc__ or "").lower()
