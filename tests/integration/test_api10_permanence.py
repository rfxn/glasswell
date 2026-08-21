"""UDM-SPEC §4.3: API-10 permanence is a measurement, not a property of the grammar (M-2).

Rev 1 of the spec quoted PPDM as certifying that an API number *is* permanent. It does not: the
fetched sentence *"urges regulators and operators to ensure that every Well Origin and Wellbore
… be assigned a permanent and unique identifier"* is an exhortation to regulators, and §2.2
supplies counter-evidence from the same source — Kern County overflowed into a second county
code, unique-well ranges differ per state, and Colorado, Michigan and Utah number specially.

What actually qualifies the API-10 as the US `native_id` is weaker and honest: it is well-origin
grained, not event-scoped, not derived from a measurement that is later recomputed, and
**observed stable across every vintage glasswell has ingested**. The fourth is a measurement,
and this file is what makes it a standing one (chunk 1.4). If a regulator ever renumbers a well,
this reddens and §4.3 gets re-argued instead of quietly becoming false.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import psycopg
from psycopg import sql

from tests.support.seed import seed_manifest, seed_well

# What the source calls the well, independent of the number being measured. `api10` itself
# cannot appear here — it is the measurand — and `api14` is deliberately excluded: its last four
# digits are a wellbore/event sequence that §2.2 records as "useful in some places, but not used
# in others", so a well that gains a sidetrack would read as a renumbering it is not.
NATIVE_IDENTITY_COLUMNS = ("ndic_file_no",)

_SIGHTINGS = sql.SQL(
    "select w.api10, w.{column} as native_id, m.fetch_vintage::text as vintage"
    "  from canonical.wells w"
    "  join lineage.manifests m on m.manifest_id = w.source_manifest_id"
    " where w.{column} is not null"
)

_RENUMBERED = sql.SQL(
    "select native_id, array_agg(distinct api10 order by api10),"
    "       array_agg(distinct api10 || ' @ ' || vintage order by api10 || ' @ ' || vintage)"
    "  from ({sightings}) seen group by native_id having count(distinct api10) > 1"
)

_REASSIGNED = sql.SQL(
    "select api10, array_agg(distinct native_id order by native_id),"
    "       array_agg(distinct native_id || ' @ ' || vintage"
    "                 order by native_id || ' @ ' || vintage)"
    "  from ({sightings}) seen group by api10 having count(distinct native_id) > 1"
)

_COVERAGE = sql.SQL(
    "select count(*) filter (where w.{column} is not null), count(*),"
    "       count(distinct m.fetch_vintage)"
    "  from canonical.wells w"
    "  join lineage.manifests m on m.manifest_id = w.source_manifest_id"
)


@dataclass(frozen=True, slots=True)
class Coverage:
    """What the measurement actually saw, so a green run cannot be an empty walk."""

    column: str
    identified_rows: int
    total_rows: int
    vintages: int

    @property
    def unmeasured_rows(self) -> int:
        """Wells this column cannot speak for — TX and NM carry no NDIC file number."""
        return self.total_rows - self.identified_rows


def permanence_coverage(connection: psycopg.Connection) -> list[Coverage]:
    found = []
    with connection.cursor() as cursor:
        for column in NATIVE_IDENTITY_COLUMNS:
            cursor.execute(_COVERAGE.format(column=sql.Identifier(column)))
            identified, total, vintages = cursor.fetchone() or (0, 0, 0)
            found.append(Coverage(column, identified, total, vintages))
    return found


def permanence_violations(connection: psycopg.Connection) -> list[str]:
    """Every well whose api10 moved, or whose api10 moved to another well, across vintages."""
    offenders: list[str] = []
    with connection.cursor() as cursor:
        for column in NATIVE_IDENTITY_COLUMNS:
            sightings = _SIGHTINGS.format(column=sql.Identifier(column))
            cursor.execute(_RENUMBERED.format(sightings=sightings))
            offenders.extend(
                f"{column} {native_id} answers to api10 {', '.join(api10s)}"
                f" — seen as {'; '.join(seen)}"
                for native_id, api10s, seen in cursor.fetchall()
            )
            cursor.execute(_REASSIGNED.format(sightings=sightings))
            offenders.extend(
                f"api10 {api10} carries {column} {', '.join(natives)}"
                f" — seen as {'; '.join(seen)}"
                for api10, natives, seen in cursor.fetchall()
            )
    return sorted(offenders)


FIRST_VINTAGE = date(2026, 6, 1)
SECOND_VINTAGE = date(2026, 8, 1)


def _vintage_manifest(connection: psycopg.Connection, when: date, sha: str) -> str:
    return seed_manifest(
        connection,
        sha256=sha,
        source_id="nd_mpr_xlsx",
        source_key=f"{when:%Y_%m}.xlsx",
        fetched_at=datetime(when.year, when.month, when.day, 5, 2, 11, tzinfo=UTC),
    )


def _two_vintages(connection: psycopg.Connection) -> tuple[str, str]:
    return (
        _vintage_manifest(connection, FIRST_VINTAGE, "a" * 64),
        _vintage_manifest(connection, SECOND_VINTAGE, "b" * 64),
    )


def test_a_well_reported_in_two_vintages_keeps_its_api10(db: psycopg.Connection) -> None:
    first, second = _two_vintages(db)
    vintages = ((first, FIRST_VINTAGE), (second, SECOND_VINTAGE))
    for index, (manifest, effective) in enumerate(vintages):
        for well in range(3):
            seed_well(
                db,
                api10=f"330531045{well}",
                effective_from=effective,
                manifest_id=manifest,
                ndic_file_no=f"1834{well}",
                status_canonical="active" if index == 0 else "plugged",
            )
    db.commit()

    coverage = permanence_coverage(db)

    assert permanence_violations(db) == []
    # N-1: a walk over one vintage would report clean without ever testing permanence.
    assert [(entry.column, entry.identified_rows, entry.vintages) for entry in coverage] == [
        ("ndic_file_no", 6, 2)
    ]


def test_a_well_renumbered_between_vintages_is_named_with_its_api10s_and_its_vintages(
    db: psycopg.Connection,
) -> None:
    """The failure §4.3 would have to be re-argued around, made legible rather than counted."""
    first, second = _two_vintages(db)
    seed_well(db, api10="3305310451", effective_from=FIRST_VINTAGE, manifest_id=first,
              ndic_file_no="18345")
    seed_well(db, api10="3305399999", effective_from=SECOND_VINTAGE, manifest_id=second,
              ndic_file_no="18345")
    db.commit()

    offenders = permanence_violations(db)

    assert offenders == [
        "ndic_file_no 18345 answers to api10 3305310451, 3305399999"
        " — seen as 3305310451 @ 2026-06-01; 3305399999 @ 2026-08-01"
    ]


def test_an_api10_reused_for_a_different_well_is_named_the_same_way(
    db: psycopg.Connection,
) -> None:
    """The other direction: the number held still and the well underneath it changed."""
    first, second = _two_vintages(db)
    seed_well(db, api10="3305310451", effective_from=FIRST_VINTAGE, manifest_id=first,
              ndic_file_no="18345")
    seed_well(db, api10="3305310451", effective_from=SECOND_VINTAGE, manifest_id=second,
              ndic_file_no="20777")
    db.commit()

    offenders = permanence_violations(db)

    assert offenders == [
        "api10 3305310451 carries ndic_file_no 18345, 20777"
        " — seen as 18345 @ 2026-06-01; 20777 @ 2026-08-01"
    ]


def test_the_measurement_reports_the_wells_it_cannot_speak_for(db: psycopg.Connection) -> None:
    """TX and NM carry no NDIC file number, and a check that hid that would be the wrong gate.

    §4.3(d) is a claim about *observed* rows. Reporting five wells clean when only two of them
    carry an identity this check can follow is the shape of gate the anti-pattern register calls
    green on data it does not represent.
    """
    first, second = _two_vintages(db)
    seed_well(db, api10="3305310451", effective_from=FIRST_VINTAGE, manifest_id=first,
              ndic_file_no="18345")
    seed_well(db, api10="3305310451", effective_from=SECOND_VINTAGE, manifest_id=second,
              ndic_file_no="18345")
    seed_well(db, api10="4200345818", effective_from=FIRST_VINTAGE, manifest_id=first,
              state_code="42", ndic_file_no=None)
    db.commit()

    coverage = permanence_coverage(db)

    assert permanence_violations(db) == []
    assert [(entry.identified_rows, entry.unmeasured_rows) for entry in coverage] == [(2, 1)]
