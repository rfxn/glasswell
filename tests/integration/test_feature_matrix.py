from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import psycopg
import pytest

from glasswell.modeling.feature_matrix import (
    EmptyFeatureMatrixError,
    FeatureMatrixError,
    build_feature_matrix,
)
from glasswell.seed import seed_all
from tests.support.seed import (
    seed_derivation,
    seed_manifest,
    seed_production,
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
            "feature_version": "fv1.0",
            "feature_set_hash": built.feature_set_hash,
            "as_of_vintage": AS_OF,
            "anchor": ANCHOR,
            "derivation_id": built.derivation_id,
            "geology.formation_group": "bakken",
            "geology.formation_group__knowable_at": ANCHOR,
        }
    ]
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
            "select document from lineage.recipes where recipe_id = %s", (built.recipe_id,)
        )
        recipe = cursor.fetchone()[0]
    assert row == (
        "features.build",
        "parquet",
        "features.well_features",
        {"feature_version": "fv1.0", "as_of_vintage": AS_OF.isoformat()},
        built.artifact_sha256,
        1,
        "1",
        built.recipe_id,
        "D1",
        "permanent",
    )
    assert all(vintage is None or vintage <= AS_OF for _, _, vintage, _ in inputs)
    assert ("external", "lineage.formation_aliases", date(2026, 8, 1), "crosswalk") in inputs
    assert recipe["output"]["sha256"] == built.artifact_sha256
    assert recipe["output"]["rows"] == 1


def test_replay_and_future_subject_production_leave_feature_bytes_unchanged(
    db, lineage_env, tmp_path: Path
):
    manifest_id, derivation_id = _seed_subject(db)
    root = tmp_path / "features"
    first = build_feature_matrix(db, as_of=AS_OF, environment=lineage_env, root=root)
    seed_production(
        db,
        api10=API10,
        production_month=date(2020, 2, 1),
        report_vintage=date(2026, 8, 1),
        volume=Decimal("999999.000"),
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )
    second = build_feature_matrix(db, as_of=AS_OF, environment=lineage_env, root=root)
    db.commit()

    assert second.derivation_id == first.derivation_id
    assert second.recipe_id == first.recipe_id
    assert second.artifact_sha256 == first.artifact_sha256
    assert second.artifact_uri == first.artifact_uri
    with db.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.derivations where derivation_id = %s",
            (first.derivation_id,),
        )
        assert cursor.fetchone()[0] == 1


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
            db, as_of=AS_OF, environment=lineage_env, root=tmp_path / "features"
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
