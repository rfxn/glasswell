"""Basin and play boundary conformance rules and the EIA sources they attach to (R8).

Dual-homed with migration 057: an already-migrated database gets these rows there, a fresh
one gets them here, and the content is the same in both homes.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

EFFECTIVE_FROM = date(2026, 8, 30)

BASINS_URL = "https://www.eia.gov/maps/map_data/SedimentaryBasins_US_EIA.zip"
PLAYS_URL = "https://www.eia.gov/maps/map_data/TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip"
MAPS_URL = "https://www.eia.gov/maps/maps.htm"

EIA_LICENSE_NOTE = (
    "US federal government work (17 U.S.C. §105). EIA publishes these map archives over"
    " anonymous HTTPS with no licence string, no terms-of-use page and no redistribution"
    " clause; the shipped FGDC metadata carries an accuracy disclaimer only. Reachability"
    " verified by anonymous GET 2026-08-30."
)

BASIN_SOURCES: tuple[dict[str, object], ...] = (
    {
        "source_id": "eia_sedimentary_basins",
        "name": "EIA sedimentary basin boundaries, lower 48 (SedimentaryBasins_US_EIA.zip)",
        "jurisdiction": "US",
        "license_note": EIA_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "eia_shale_plays",
        "name": "EIA tight oil and shale gas individual play boundaries, lower 48"
        " (TightOil_ShaleGas_IndividualPlays_Lower48_EIA.zip)",
        "jurisdiction": "US",
        "license_note": EIA_LICENSE_NOTE,
        "redistributable": False,
    },
)

BASIN_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_eia_boundary_publisher_1",
        "source_id": "eia_shale_plays",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom", "boundary_id", "name"],
        "spec": {
            "module_function": "glasswell.ingest.eia_boundaries:LAYERS",
            "version": "1",
            "publisher": "US Energy Information Administration",
            "archives": {
                "basins": {
                    "url": BASINS_URL,
                    "shapefile": "SedimentaryBasins_US_May2011_v2",
                    "bytes": 440871,
                    "sha256": "02a017ccb84bdcc15726838098e3cfa73450b9655cf06e28d2eca6f3c04edcff",
                    "upstream_last_modified": "2016-03-10T16:39:22Z",
                    "features": 32,
                },
                "plays": {
                    "url": PLAYS_URL,
                    "bytes": 2931129,
                    "sha256": "20be8ea37727b05fc83e234a3257c069df5e5771b74501f40fc0828a7195c84b",
                    "upstream_last_modified": "2019-01-22T18:17:21Z",
                    "features": 16,
                    "shapefiles": 12,
                },
            },
            "rejected_publishers": [
                "USGS National Oil and Gas Assessment assessment units",
                "state survey basin outlines (ND DMR, TX RRC, NM BGMR)",
            ],
            "identity": "EIA publishes no feature id on either layer, so the key is minted"
            " here: basin_<slug(NAME)> and play_<slug(Shale_play)>_<slug(Basin)>. The play"
            " pair is the key rather than the play name alone because Niobrara is published"
            " as five features under five different Basin labels. Minting a key is a"
            " decision: a publisher that later ships its own id supersedes this row.",
            "contract_note": "canonical.basin_boundaries and both boundary tile layers carry"
            " this publisher's own names and areas verbatim under a minted key; the ingest"
            " module is the executor, and a different publisher is a superseding row, not a"
            " code change",
        },
        "rule": "Draw basin and play boundaries from the EIA lower-48 map archives; USGS"
        " assessment units and state-survey outlines are cross-checks, not sources.",
        "rationale": (
            "The boundary layers a map needs are a published interpretation, and the choice"
            " of whose interpretation is the decision. EIA was taken over the USGS National"
            " Oil and Gas Assessment because it publishes basin and play as two separate"
            " archives with a stated distinction between them, which is the distinction this"
            " repository has to keep; USGS assessment units are chosen for assessment"
            " arithmetic and slice the same rock differently, so adopting them would import a"
            " boundary set whose purpose is not cartographic reference. Both EIA archives are"
            " plain anonymous HTTPS zips, so neither goes through the ArcGIS host allowlist"
            " (blueprint v0.6 §4E.7) and neither needs an amendment to it. The vintages are"
            " old and stated rather than hidden: the basin layer is EIA's May 2011 compilation"
            " republished 2016-03-10, and the play archive is a 2019-01-22 bundle whose"
            " members carry per-feature vintages between Aug 2015 and Sep 2018. A boundary is"
            " never authoritative here — it is one agency's published interpretation at a"
            " vintage, and vintage_label says which one on every served feature."
        ),
        "evidence_url": MAPS_URL,
        "code_ref": "src/glasswell/ingest/eia_boundaries.py",
    },
    {
        "rule_id": "cr_eia_boundary_taxonomy_1",
        "source_id": "eia_shale_plays",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["boundary_kind", "name", "basin_name", "sub_basin"],
        "spec": {
            "module_function": "glasswell.ingest.eia_boundaries:LAYERS",
            "version": "1",
            "boundary_kind": {
                "basin": "a structural sedimentary basin outline: the depositional container,"
                " independent of what is producible in it. 32 features, one layer.",
                "play": "a producible interval's mapped extent inside one or more basins."
                " 16 features over 12 shapefiles, each with its own vintage.",
            },
            "never_merged": "the two kinds share canonical.basin_boundaries and are"
            " discriminated by boundary_kind; they are published as two tile layers and are"
            " never unioned, because a play extent inside a basin is not a smaller basin",
            "sub_basin": "carried only where the publisher states one. Wolfcamp is the only"
            " feature that does (SubBasin = Delaware); Delaware and Midland are also published"
            " as plays in their own right, which is the publisher's inconsistency and is"
            " reproduced rather than reconciled",
            "contract_note": "marts.basin_boundaries_tile and both boundary tile layers carry"
            " boundary_kind on every feature; the ingest module is the executor, and merging"
            " or re-classing the two kinds is a superseding row, not a code change",
        },
        "rule": "A basin and a play are different objects and are stored under one table with"
        " an explicit boundary_kind discriminator, never conflated and never unioned.",
        "rationale": (
            "The two words are used interchangeably in trade press and they are not"
            " interchangeable: the Permian basin is one structural container and Wolfcamp,"
            " Bone Spring, Spraberry, Delaware, Abo-Yeso and Glorieta-Yeso are six mapped"
            " producible extents inside it, five of which overlap. A single 'basin' layer"
            " that flattened both would make 'wells in the Permian' answerable two ways with"
            " no way to tell which was meant. One table with a discriminator keeps the"
            " hierarchy joinable without asserting that a play is a kind of basin."
        ),
        "evidence_url": PLAYS_URL,
        "code_ref": "src/glasswell/ingest/eia_boundaries.py",
    },
    {
        "rule_id": "cr_eia_basin_link_1",
        "source_id": "eia_shale_plays",
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["basin_name", "basin_boundary_id"],
        "spec": {
            "module_function": "glasswell.ingest.eia_boundaries:_promote_plays",
            "version": "1",
            "match": "case-folded exact equality between the play layer's own Basin string"
            " and the basin layer's NAME; no suffix stripping, no token overlap, no fuzzy"
            " distance",
            "unresolved": "basin_boundary_id stays null and basin_name keeps the publisher's"
            " string verbatim; a play is never dropped for failing to link",
            "measured_2026_08_30": {
                "play_features": 16,
                "resolved": 12,
                "unresolved": 4,
                "refused_near_matches": {
                    "Piceance Basin": "the basin layer publishes UINTA-PICEANCE, a combined"
                    " outline that is materially larger than the Piceance alone; linking"
                    " would silently widen the play's parent",
                    "Denver Basin": "the basin layer publishes DENVER; the strings differ"
                    " only by the word Basin, and stripping it is a transform that would also"
                    " have to be defended for Piceance and Park, where it is wrong",
                    "Park Basin": "the basin layer publishes NORTH PARK; whether the play's"
                    " Park is North Park, Middle Park or both is not stated by the publisher",
                    "North-Central MT": "a geographic descriptor, not a basin name; the basin"
                    " layer publishes no feature it can mean",
                },
            },
            "contract_note": "canonical.basin_boundaries.basin_boundary_id is populated only"
            " by this rule and only for plays; the promotion refuses to run before the basin"
            " layer is loaded, so a null link means the name did not resolve and never means"
            " the basin layer was absent",
        },
        "rule": "A play links to a basin by case-folded exact name match against the basin"
        " layer, and links to nothing when the name does not resolve.",
        "rationale": (
            "The two EIA archives are separate publications with no shared key, so the only"
            " join available is on a name string, and four of sixteen plays do not resolve:"
            " Piceance Basin, Denver Basin, Park Basin and North-Central MT. Each is a near"
            " miss with a plausible repair and each repair is a different guess — strip the"
            " word Basin and Denver resolves correctly while Piceance resolves into"
            " UINTA-PICEANCE, a larger container the publisher did not name. A join that is"
            " right twelve times and quietly wrong twice is worse than one that reports four"
            " unresolved links, because only the second is visible at /conformance. The"
            " publisher's own string is kept on the row either way, so a later rule can"
            " supersede this one with a stated crosswalk rather than re-deriving it."
        ),
        "evidence_url": PLAYS_URL,
        "code_ref": "src/glasswell/ingest/eia_boundaries.py",
    },
    {
        "rule_id": "cr_eia_boundary_overlap_1",
        "source_id": "eia_shale_plays",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom"],
        "spec": {
            "module_function": "glasswell.marts.basin_boundaries:refresh_basin_boundaries",
            "version": "1",
            "policy": "boundaries are stored and served exactly as published: never"
            " dissolved, never clipped to one another, never assigned a precedence order",
            "membership_is_a_set": "a point may be inside zero, one or several plays and"
            " inside zero or one basins; any consumer needing a single value must name its own"
            " arbitration rule, which is a new conformance row and not a default here",
            "measured_2026_08_30": {
                "permian_plays_overlapping": [
                    "Wolfcamp", "Bone Spring", "Spraberry", "Delaware", "Abo-Yeso",
                    "Glorieta-Yeso",
                ],
                "williston_plays_overlapping": ["Bakken", "Three Forks"],
                "note": "Bakken and Three Forks are stacked intervals over almost the same"
                " footprint; a dissolve would erase the fact that they are two targets",
            },
            "outside_everything": "a point inside no published boundary is unassigned. It is"
            " never defaulted to the nearest boundary and never to a basin implied by its"
            " state.",
            "contract_note": "marts.basin_boundaries_tile carries one row per published"
            " feature with its geometry unaltered except for the repair cr_eia_geometry"
            "_repair_1 governs; a de-overlapped or dissolved surface is a superseding row",
        },
        "rule": "Published boundaries overlap and are served overlapping; membership is a set,"
        " there is no precedence, and a location inside none of them is unassigned.",
        "rationale": (
            "Play polygons nest and intersect by construction — six Permian plays share the"
            " same ground because they are stacked intervals, not neighbouring territories."
            " Dissolving them into a partition would produce a tidy map that answers the"
            " wrong question, and picking a precedence order would bury a ranking decision in"
            " a mart. Serving the overlap is the honest surface: it shows the reader that the"
            " Permian is six targets, and it forces any single-valued basin or play attribute"
            " downstream to declare the arbitration it used."
        ),
        "evidence_url": PLAYS_URL,
        "code_ref": "src/glasswell/marts/basin_boundaries.py",
    },
    {
        "rule_id": "cr_eia_geometry_repair_1",
        "source_id": "eia_shale_plays",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom", "geometry_repair", "geometry_repair_reason"],
        "spec": {
            "module_function": "glasswell.ingest.eia_boundaries:_promote_plays",
            "version": "1",
            "test": "ST_IsValid on the staged geometry, which holds the source bytes verbatim",
            "repair": "ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) — polygonal"
            " components only, so a repair that sheds a degenerate spike sheds it rather than"
            " smuggling a line into a polygon column",
            "refusal": "a repair whose result is empty or not polygonal is refused: the row is"
            " quarantined invalid_geometry and never promoted",
            "never_silent": "every repaired feature is written to lineage.quarantine_rows"
            " with reason_code invalid_geometry and ST_IsValidReason as evidence, then"
            " released under this rule id with the promotion derivation recorded. The row"
            " carries geometry_repair and geometry_repair_reason so the repair is visible"
            " without reading the ledger.",
            "measured_2026_08_30": {
                "features_examined": 48,
                "invalid": 2,
                "invalid_features": {
                    "Bakken": "Ring Self-intersection at -101.784379615, 48.9030813580001",
                    "Three Forks": "Ring Self-intersection at -103.224838549,"
                    " 46.7023706000001",
                },
                "relative_area_change": "below 1e-15 for both, i.e. the repair closes a"
                " self-touching ring and moves no boundary a reader could see",
                "three_forks_note": "ST_MakeValid returns a GeometryCollection for Three"
                " Forks, which is why the extract step is part of the repair and not an"
                " afterthought",
            },
            "contract_note": "canonical.basin_boundaries.geometry_repair names the repair"
            " applied to each row and is null where none was; repairing by any other operator,"
            " or promoting an unrepairable geometry, is a superseding row",
        },
        "rule": "An invalid published boundary is repaired by ST_MakeValid with polygonal"
        " extraction, recorded as a released quarantine row, and refused outright when the"
        " repair does not yield a polygon.",
        "rationale": (
            "Two of the forty-eight published features are invalid, and both are Williston"
            " plays — the two this repository most needs to draw. Quarantining them would"
            " remove the Bakken from a Bakken product to uphold a rule about ring topology;"
            " silently repairing them would put a geometry on the map that no publisher"
            " published. The third option is the one taken: repair, but make the repair a"
            " fact. The reject is written with its reason code and ST_IsValidReason before it"
            " is released under this rule, so /v1/quarantine shows a released row rather than"
            " nothing at all, and the measured area change is recorded so a future reader can"
            " see the repair was topological and not cartographic. A repair that cannot"
            " return a polygon is not a repair and is refused."
        ),
        "evidence_url": PLAYS_URL,
        "code_ref": "src/glasswell/ingest/eia_boundaries.py",
    },
    {
        "rule_id": "cr_eia_area_provenance_1",
        "source_id": "eia_shale_plays",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["area_sq_mi", "area_basis"],
        "spec": {
            "module_function": "glasswell.marts.basin_boundaries:refresh_basin_boundaries",
            "version": "1",
            "area_basis": "publisher_reported",
            "published_field": "Area_sq_mi on both archives, carried through unrecomputed and"
            " rounded to two decimals at the mart boundary",
            "not_recomputed": "glasswell does not measure these polygons. EIA states no"
            " equal-area projection for the figure, so a recomputed area would differ from the"
            " published one by an unstated amount and there would be two areas on the map.",
            "handle": "every served area rides marts.basin_boundaries_tile alongside the"
            " refresh derivation_id, which /v1/explain resolves to the manifest the figure"
            " came from — the figure is the publisher's, and the handle says so",
            "contract_note": "area_sq_mi is the publisher's own number and area_basis names"
            " it as such on every row; computing an area here is a superseding row that must"
            " state its projection",
        },
        "rule": "The served area is the publisher's own Area_sq_mi, labelled"
        " publisher_reported, never recomputed by glasswell.",
        "rationale": (
            "An area is a figure and R6 gives it a handle, but the handle has to resolve to"
            " the truth. Recomputing the area in an equal-area projection would produce a"
            " number glasswell could defend and EIA never published, sitting next to a name"
            " and a boundary that are EIA's — a mixed-provenance row that reads as one"
            " source's. Carrying the published figure with area_basis stating its origin keeps"
            " the whole row attributable to one publication, and leaves recomputation to a"
            " superseding rule that would have to name the projection it used."
        ),
        "evidence_url": BASINS_URL,
        "code_ref": "src/glasswell/marts/basin_boundaries.py",
    },
    {
        "rule_id": "cr_eia_well_membership_1",
        "source_id": "eia_shale_plays",
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom", "boundary_id", "api10"],
        "spec": {
            "module_function": "glasswell.marts.basin_boundaries:refresh_basin_boundaries",
            "version": "1",
            "test": "ST_Intersects between the well's surface-hole point and the boundary"
            " polygon, in EPSG:4326, evaluated against the served boundary geometry",
            "anchor": "the surface hole. The lateral midpoint anchor cr_land_agg_membership_1"
            " uses is a section-grain choice; at basin grain a lateral is far shorter than the"
            " smallest boundary and the two anchors agree except at a boundary edge, so the"
            " simpler anchor is stated rather than the more elaborate one being borrowed.",
            "multiple": "a well may be inside several plays; membership is the set of"
            " boundaries it intersects, per cr_eia_boundary_overlap_1, and is not collapsed",
            "unassigned": "a well inside no boundary is unassigned. It is never defaulted to a"
            " basin implied by its state or its operator.",
            "not_the_wells_basin_column": "canonical.wells.basin is a per-source declared"
            " constant written by the ND and TX ingests, not a geometric test against these"
            " boundaries, and the two must not be read as the same claim. All 43,817 ND wells"
            " carry basin=williston because the ND ingest declares it, not because anything"
            " tested a point against the Williston outline.",
            "no_stored_membership_yet": "as of this rule's effective date glasswell serves the"
            " boundaries and stores no well-to-boundary assignment. This row is the definition"
            " any basin-scoped rollup must implement, registered before the first consumer"
            " rather than after it.",
            "contract_note": "any served figure scoped to a basin or play must cite this rule"
            " or a superseding one; a rollup that assigns wells by a different anchor, or that"
            " collapses multi-play membership to a single value, is a superseding row",
        },
        "rule": "A well is inside a basin or play when its surface hole intersects that"
        " boundary; membership is a set, and a well inside none of them is unassigned.",
        "rationale": (
            "The map already labels every North Dakota well basin=williston, and that label"
            " comes from a constant in the ND ingest rather than from any boundary — exactly"
            " the mapping-in-code R8 exists to refuse. Registering the geometric definition"
            " now, before the first basin-scoped rollup is built, means the rollup inherits a"
            " written membership test instead of inventing one, and means the existing"
            " declared-constant column is on the record as a different claim from the"
            " geometric one. No stored assignment is derived here: the boundaries are the"
            " spine, and a membership mart is the consumer this definition is waiting for."
        ),
        "evidence_url": PLAYS_URL,
        "code_ref": "src/glasswell/marts/basin_boundaries.py",
    },
    {
        "rule_id": "cr_eia_boundary_datum_1",
        "source_id": "eia_shale_plays",
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["geom"],
        "spec": {
            "source_epsg": 4326,
            "target_epsg": 4326,
            "detect": {"prj_geogcs": "GCS_WGS_1984"},
        },
        "rule": "Both EIA boundary archives ship WGS 84 geographic coordinates; the transform"
        " to EPSG:4326 storage is the identity and is still asserted on every fetch.",
        "rationale": (
            "Every .prj in both archives resolves to EPSG:4326, so the transform does nothing"
            " — which is precisely why it is a row. The datum is read from the shipped .prj"
            " through the strict resolver and compared against this rule before a coordinate"
            " is staged, so a republished archive in a different frame fails loudly instead of"
            " landing silently shifted. No datum is ever defaulted (same rule as cr_nd_datum_1"
            " and cr_blm_plss_datum_1)."
        ),
        "evidence_url": BASINS_URL,
    },
)

_INSERT_SOURCE = """
insert into lineage.sources (source_id, name, jurisdiction, license_note, redistributable)
values (%(source_id)s, %(name)s, %(jurisdiction)s, %(license_note)s, %(redistributable)s)
on conflict do nothing
"""

_INSERT_RULE = """
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
values (%(rule_id)s, %(rule_family)s, %(supersedes_rule_id)s, %(source_id)s, %(stage)s,
        %(applies_to_fields)s, %(rule_kind)s, %(spec)s, %(rule)s, %(rationale)s,
        %(evidence_url)s, %(code_ref)s, %(effective_from)s)
on conflict do nothing
"""


def _row(rule: dict[str, object]) -> dict[str, object]:
    rule_id = str(rule["rule_id"])
    return {
        **rule,
        "rule_family": rule_id.rsplit("_", 1)[0],
        "spec": Jsonb(rule["spec"]),
        "code_ref": rule.get("code_ref"),
        "evidence_url": rule.get("evidence_url"),
        "supersedes_rule_id": rule.get("supersedes_rule_id"),
        "effective_from": rule.get("effective_from", EFFECTIVE_FROM),
    }


def seed_sources_basins(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_SOURCE, BASIN_SOURCES)
    return len(BASIN_SOURCES)


def seed_conformance_basins(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a change is a new row with supersedes_rule_id (SB-07 §6.2)."""
    seed_sources_basins(connection)
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, [_row(rule) for rule in BASIN_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id like 'cr\\_eia\\_%'"
        )
        return int(cursor.fetchone()[0])
