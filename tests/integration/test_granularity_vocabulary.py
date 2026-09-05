"""M-5: one granularity vocabulary, enforced identically at the store and at the wire.

Reconciliation S-B composes `granularity` and `reporting_level` into the served token:
`(observed, well) → well_observed`, `(observed, well_completion_pool) → well_observed` with an
aggregation, `(observed, lease) → lease_reported`, `(allocated, well) → lease_allocated`. Four
mappings, three tokens. The DB admitted two of them and the serializer a different two.

What the composed token set *is*, and that a token outside it is refused, needs no database and
lives in `tests/unit/test_envelope.py`; both halves of the comparison below are here.
"""

from __future__ import annotations

import re

from glasswell.lineage.envelope import GRANULARITIES, figure

_LITERAL_RE = re.compile(r"'([a-z_]+)'::text")
_CONSTRAINT = """
select pg_get_constraintdef(c.oid)
  from pg_constraint c
  join pg_class t on t.oid = c.conrelid
  join pg_namespace n on n.oid = t.relnamespace
 where n.nspname = 'canonical' and t.relname = 'production_monthly'
   and c.contype = 'c' and pg_get_constraintdef(c.oid) like '%granularity%'
"""

# `lease_allocated` needs an allocation model id, and bbl needs a liquids basis.
_EXTRA = {"lease_allocated": {"allocation_model_id": "mdl_test"}}


def admitted_granularities(connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(_CONSTRAINT)
        rows = cursor.fetchall()
    assert rows, "canonical.production_monthly has no granularity CHECK to read"
    return set(_LITERAL_RE.findall(rows[0][0]))


def test_the_store_and_the_serializer_hold_the_same_vocabulary(db):
    assert admitted_granularities(db) == set(GRANULARITIES)


def test_every_granularity_the_store_admits_serializes(db):
    """A canonical row the serializer refuses is an unhandled ValueError, i.e. a 500."""
    for granularity in sorted(admitted_granularities(db)):
        served = figure(
            "1.0",
            unit="bbl",
            derivation="drv_granularity_probe",
            granularity=granularity,
            basis="oil+condensate",
            **_EXTRA.get(granularity, {}),
        )
        assert served.granularity == granularity


