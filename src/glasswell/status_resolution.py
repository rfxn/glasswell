"""Read-time resolution of a canonical well status from the conformance registry.

`canonical.wells.status_canonical` is null for every New Mexico header and stays that way: the
table is append-only and a re-promotion would have to invent a valid time the OCD never filed
(cr_nm_wellhistory_status_vocab_2). The class is therefore a join, and it lives here rather
than at any one call site so that the tile mart, the well card and the status summary cannot
answer differently on the same screen.
"""

from __future__ import annotations

RESOLVER_VIEW = "canonical.status_resolution"
RESOLVER_RULES = {"30": "cr_nm_wellhistory_status_vocab_2"}


def resolver_join(spine: str, *, resolver: str = "sr") -> str:
    """Left join `spine` onto the resolver on its state code and reported status."""
    return (
        f" left join {RESOLVER_VIEW} {resolver}"
        f" on {resolver}.for_state_code = {spine}.state_code"
        f" and {resolver}.for_status_reported = {spine}.status_reported"
    )


def resolved_status(spine: str, *, resolver: str = "sr") -> str:
    """The served class: what the promotion wrote, else what the registry resolves."""
    return f"coalesce({spine}.status_canonical, {resolver}.resolved_status)"
