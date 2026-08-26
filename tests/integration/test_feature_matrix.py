from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl
import psycopg
import pytest

from glasswell.modeling.feature_matrix import (
    ConflictingFeatureValueError,
    EmptyFeatureMatrixError,
    FeatureMatrixError,
    build_feature_matrix,
)
from glasswell.seed import seed_all
from tests.support.seed import (
    seed_derivation,
    seed_manifest,
    seed_well,
)

AS_OF = date(2026, 8, 2)
ANCHOR = date(2020, 1, 15)
API10 = "3305300001"


def _seed_subject(db) -> tuple[str, str]:
    seed_all(db)
    manifest_id = seed_manifest(db, sha256="a" * 64)
    derivation_id = seed_derivation(db)
    seed_well(
        db,
        api10=API10,
        completion_date=ANCHOR,
        effective_from=date(2026, 8, 1),
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, source_id, created_vintage)"
            " values ('BAKKEN', 'bakken', 0.990, '2026-08-01', 'nd_mpr_xlsx', '2026-08-01')"
        )
        cursor.execute(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
            " production_month, report_vintage, source_manifest_id, derivation_id)"
            " values ('3305300001:BAKKEN', %s, 'BAKKEN', 'BAKKEN', 'nd_mpr_xlsx',"
            " '2020-02-01', '2026-08-01', %s, %s)",
            (API10, manifest_id, derivation_id),
        )
    return manifest_id, derivation_id


def test_feature_matrix_is_guarded_content_addressed_and_lineage_complete(
    db, lineage_env, tmp_path: Path
):
    _seed_subject(db)

    built = build_feature_matrix(
        db, as_of=AS_OF, environment=lineage_env, root=tmp_path / "features"
    )
    db.commit()

    artifact = Path(built.artifact_uri)
    assert artifact.is_file()
    assert artifact.parent.name == f"sha256={built.artifact_sha256}"
    assert built.rows == 1
    frame = pl.read_parquet(artifact)
    assert frame.to_dicts() == [
        {
            "api10": API10,
            "feature_version": "fv2.0",
            "feature_set_hash": built.feature_set_hash,
            "as_of_vintage": AS_OF,
            "anchor": ANCHOR,
            "derivation_id": built.derivation_id,
            "geology.formation_group": "bakken",
            "geology.formation_group__knowable_at": ANCHOR,
            "geology.formation_group__source_available_on": date(2020, 3, 17),
        }
    ]
    coverage = json.loads(Path(built.coverage_uri).read_bytes())
    assert coverage["counts"] == {
        "anchor_status": {"anchor_before_first_source_month": 1},
        "conflicts": 0,
        "missing": 0,
        "resolved": 1,
        "subjects": 1,
    }
    assert coverage["publication_lag_measurement"]["p50_days"] == 82
    assert coverage["retrospective_vintage"] == {
        "matrix_basis": "strict_manifest_knowledge",
        "pre_history_floor_policy": "unavailable_not_fabricated",
        "source_replay_basis": "source_reconstructed_not_glasswell_history",
        "source_replay_field": "geology.formation_group__source_available_on",
    }
    with db.cursor() as cursor:
        cursor.execute(
            "select operation, output_store, output_dataset, output_partition, output_sha256,"
            " output_rows, output_schema_version, recipe_id, determinism_class, ttl_class"
            " from lineage.derivations where derivation_id = %s",
            (built.derivation_id,),
        )
        row = cursor.fetchone()
        cursor.execute(
            "select kind, ref_id, as_of_vintage, role from lineage.derivation_inputs"
            " where derivation_id = %s order by ord",
            (built.derivation_id,),
        )
        inputs = cursor.fetchall()
        cursor.execute(
            "select selector from lineage.derivation_inputs"
            " where derivation_id = %s and ref_id = 'lineage.formation_aliases'",
            (built.derivation_id,),
        )
        alias_selector = cursor.fetchone()[0]
        cursor.execute(
            "select document from lineage.recipes where recipe_id = %s", (built.recipe_id,)
        )
        recipe = cursor.fetchone()[0]
    assert row == (
        "features.build",
        "parquet",
        "features.well_features",
        {"feature_version": "fv2.0", "as_of_vintage": AS_OF.isoformat()},
        built.artifact_sha256,
        1,
        "2",
        built.recipe_id,
        "D1",
        "permanent",
    )
    assert all(vintage is None or vintage <= AS_OF for _, _, vintage, _ in inputs)
    assert ("external", "lineage.formation_aliases", date(2026, 8, 1), "crosswalk") in inputs
    assert alias_selector.startswith("sha256:")
    assert recipe["output"]["sha256"] == built.artifact_sha256
    assert recipe["output"]["coverage"] == {
        "filename": "coverage.json",
        "sha256": built.coverage_sha256,
    }
    assert recipe["output"]["rows"] == 1


def test_replay_and_future_subject_pool_observations_leave_feature_bytes_unchanged(
    db, lineage_env, tmp_path: Path
):
    manifest_id, derivation_id = _seed_subject(db)
    root = tmp_path / "features"
    first = build_feature_matrix(db, as_of=AS_OF, environment=lineage_env, root=root)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('MADISON', 'madison', 0.990, '2026-08-01', 'nd_mpr_xlsx', '2026-08-01')"
        )
        cursor.execute(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
            " production_month, report_vintage, source_manifest_id, derivation_id)"
            " values ('3305300001:MADISON', %s, 'MADISON', 'MADISON', 'nd_mpr_xlsx',"
            " '2021-01-01', '2026-08-01', %s, %s)",
            (API10, manifest_id, derivation_id),
        )
    second = build_feature_matrix(db, as_of=AS_OF, environment=lineage_env, root=root)
    db.commit()

    assert second.derivation_id == first.derivation_id
    assert second.recipe_id == first.recipe_id
    assert second.artifact_sha256 == first.artifact_sha256
    assert second.artifact_uri == first.artifact_uri
    assert second.coverage_sha256 == first.coverage_sha256
    assert second.coverage_uri == first.coverage_uri
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.derivations where derivation_id = %s",
            (first.derivation_id,),
        )
        assert cursor.fetchone()[0] == 1


def test_initial_month_conflict_is_null_and_published_without_changing_fv1(
    db, lineage_env, tmp_path
):
    manifest_id, derivation_id = _seed_subject(db)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('MADISON', 'madison', 0.990, '2026-08-01', 'nd_mpr_xlsx', '2026-08-01')"
        )
        cursor.execute(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
            " production_month, report_vintage, source_manifest_id, derivation_id)"
            " values ('3305300001:MADISON', %s, 'MADISON', 'MADISON', 'nd_mpr_xlsx',"
            " '2020-02-01', '2026-08-01', %s, %s)",
            (API10, manifest_id, derivation_id),
        )

    built = build_feature_matrix(
        db, as_of=AS_OF, environment=lineage_env, root=tmp_path / "features-v2"
    )
    frame = pl.read_parquet(built.artifact_uri)
    coverage = json.loads(Path(built.coverage_uri).read_bytes())

    assert frame["geology.formation_group"].item() is None
    assert coverage["counts"]["conflicts"] == 1
    assert coverage["conflicts"] == [
        {
            "api10": API10,
            "first_source_month": "2020-02-01",
            "formation_groups": ["bakken", "madison"],
            "reported_pools": ["BAKKEN", "MADISON"],
        }
    ]
    with pytest.raises(ConflictingFeatureValueError, match="resolves to"):
        build_feature_matrix(
            db,
            as_of=AS_OF,
            environment=lineage_env,
            feature_version="fv1.0",
            root=tmp_path / "features-v1",
        )


def test_initial_month_ignores_null_pools_and_other_sources(db, lineage_env, tmp_path: Path):
    manifest_id, _ = _seed_subject(db)
    foreign_manifest_id = seed_manifest(
        db,
        sha256="c" * 64,
        source_id="tx_pdq_dsv",
        source_key="foreign.csv",
    )
    contaminant_derivation_id = seed_derivation(
        db,
        params={"source_key": "foreign.csv"},
        partition={"source_id": "tx_pdq_dsv"},
    )
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('MADISON', 'madison', 0.990, '2026-08-01', 'nd_mpr_xlsx', '2026-08-01')"
        )
        cursor.execute(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
            " production_month, report_vintage, source_manifest_id, derivation_id) values"
            " ('3305300001:UNKNOWN', %s, 'UNKNOWN', null, 'nd_mpr_xlsx',"
            " '2019-11-01', '2026-08-01', %s, %s),"
            " ('3305300001:FOREIGN', %s, 'MADISON', 'MADISON', 'tx_pdq_dsv',"
            " '2019-12-01', '2026-08-01', %s, %s)",
            (
                API10,
                manifest_id,
                contaminant_derivation_id,
                API10,
                foreign_manifest_id,
                contaminant_derivation_id,
            ),
        )

    built = build_feature_matrix(
        db, as_of=AS_OF, environment=lineage_env, root=tmp_path / "features"
    )
    frame = pl.read_parquet(built.artifact_uri)
    with db.cursor() as cursor:
        cursor.execute(
            "select ref_id from lineage.derivation_inputs where derivation_id = %s",
            (built.derivation_id,),
        )
        input_ids = {row[0] for row in cursor.fetchall()}

    assert frame["geology.formation_group"].item() == "bakken"
    assert frame["geology.formation_group__source_available_on"].item() == date(2020, 3, 17)
    assert contaminant_derivation_id not in input_ids


def test_future_knowledge_does_not_enter_an_older_matrix(db, lineage_env, tmp_path: Path):
    _seed_subject(db)
    root = tmp_path / "features"
    first = build_feature_matrix(db, as_of=AS_OF, environment=lineage_env, root=root)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, source_id, created_vintage)"
            " values ('BAKKEN', 'not_bakken', 0.999, '2026-08-02', 'nd_mpr_xlsx', '2026-08-03')"
        )
    second = build_feature_matrix(db, as_of=AS_OF, environment=lineage_env, root=root)

    assert second.artifact_sha256 == first.artifact_sha256
    assert pl.read_parquet(second.artifact_uri)["geology.formation_group"].item() == "bakken"


def test_relevant_same_vintage_alias_revision_changes_derivation_identity(
    db, lineage_env, tmp_path: Path
):
    _seed_subject(db)
    first = build_feature_matrix(
        db, as_of=AS_OF, environment=lineage_env, root=tmp_path / "features-first"
    )
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('BAKKEN', 'not_bakken', 0.999, '2026-08-02', 'nd_mpr_xlsx', '2026-08-02')"
        )
    second = build_feature_matrix(
        db, as_of=AS_OF, environment=lineage_env, root=tmp_path / "features-second"
    )

    assert second.derivation_id != first.derivation_id
    assert second.artifact_sha256 != first.artifact_sha256
    assert pl.read_parquet(second.artifact_uri)["geology.formation_group"].item() == "not_bakken"


def test_live_regime_refuses_to_emit_a_matrix_without_completion_anchors(
    db, lineage_env, tmp_path: Path
):
    seed_all(db)

    with pytest.raises(EmptyFeatureMatrixError, match="completion_date anchor"):
        build_feature_matrix(
            db, as_of=AS_OF, environment=lineage_env, root=tmp_path / "features"
        )

    assert list((tmp_path / "features").rglob("*.parquet")) == []


def test_matrix_refuses_to_persist_when_every_registered_value_is_missing(
    db, lineage_env, tmp_path: Path
):
    seed_all(db)
    manifest_id = seed_manifest(db, sha256="b" * 64)
    derivation_id = seed_derivation(db)
    seed_well(
        db,
        api10=API10,
        completion_date=ANCHOR,
        effective_from=date(2026, 8, 1),
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )

    with pytest.raises(EmptyFeatureMatrixError, match="no registered feature value"):
        build_feature_matrix(
            db,
            as_of=AS_OF,
            environment=lineage_env,
            feature_version="fv1.0",
            root=tmp_path / "features",
        )

    assert list((tmp_path / "features").rglob("*.parquet")) == []


def test_unvintaged_aliases_are_rejected_instead_of_treated_as_historical_knowledge(
    db, lineage_env, tmp_path: Path
):
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, source_id)"
            " values ('BAKKEN', 'bakken', 0.990, '2020-01-01', 'nd_mpr_xlsx')"
        )

    with pytest.raises(FeatureMatrixError, match="lack created_vintage"):
        build_feature_matrix(
            db, as_of=AS_OF, environment=lineage_env, root=tmp_path / "features"
        )


def test_formation_alias_knowledge_history_is_append_only(db):
    seed_all(db)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, confidence, effective_from, source_id, created_vintage)"
            " values ('BAKKEN', 'bakken', 0.990, '2020-01-01', 'nd_mpr_xlsx', '2026-08-01')"
        )
    db.commit()

    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        with db.cursor() as cursor:
            cursor.execute(
                "update lineage.formation_aliases set formation = 'three_forks'"
                " where formation_raw = 'BAKKEN'"
            )
    db.rollback()
