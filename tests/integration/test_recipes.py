from __future__ import annotations

import pytest

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.recipes import build_recipe
from glasswell.lineage.store import PostgresRecorder
from tests.support.seed import seed_manifest

CLOSURE = {
    "code_version": "git:9f2c1ab",
    "lockfile_sha256": "d" * 64,
    "entry_point": "glasswell.ingest.nd_mpr:promote",
    "params": {"month_convention": "production_month"},
    "input_manifest_ids": ["man_" + "a" * 32],
}


def test_a_recipe_is_stored_with_the_closure_that_regenerates_the_artifact(db):
    recipe_id = build_recipe(db, "canonical.promote", **CLOSURE)
    db.commit()

    assert recipe_id.startswith("rcp_")
    with db.cursor() as cursor:
        cursor.execute(
            "select operation, document from lineage.recipes where recipe_id = %s", (recipe_id,)
        )
        operation, document = cursor.fetchone()
    assert operation == "canonical.promote"
    assert document["recipe_id"] == recipe_id
    assert document["environment"]["lockfile_sha256"] == "d" * 64
    assert document["determinism_class"] == "D1"
    assert document["inputs"] == [{"kind": "manifest", "id": "man_" + "a" * 32}]
    assert document["replay"] == f"glasswell repro {recipe_id}"


def test_an_identical_closure_addresses_the_same_recipe_row(db):
    first = build_recipe(db, "canonical.promote", **CLOSURE)
    second = build_recipe(db, "canonical.promote", **CLOSURE)
    db.commit()

    assert first == second
    with db.cursor() as cursor:
        cursor.execute("select count(*) from lineage.recipes")
        assert cursor.fetchone()[0] == 1


def test_a_changed_parameter_addresses_a_different_recipe(db):
    first = build_recipe(db, "canonical.promote", **CLOSURE)
    second = build_recipe(
        db, "canonical.promote", **{**CLOSURE, "params": {"month_convention": "report_month"}}
    )
    assert first != second


def test_a_recipe_can_bind_non_manifest_inputs_and_the_expected_output(db):
    recipe_id = build_recipe(
        db,
        "features.build",
        **{
            **CLOSURE,
            "input_manifest_ids": (),
            "input_refs": [
                InputRef(
                    kind="derivation",
                    ref_id="drv_input",
                    as_of_vintage="2026-08-01",
                )
            ],
            "output": {
                "dataset": "features.well_features",
                "sha256": "f" * 64,
                "determinism_class": "D1",
            },
        },
    )
    db.commit()

    with db.cursor() as cursor:
        cursor.execute("select document from lineage.recipes where recipe_id = %s", (recipe_id,))
        document = cursor.fetchone()[0]
    assert document["inputs"] == [
        {
            "as_of_vintage": "2026-08-01",
            "kind": "derivation",
            "ord": 0,
            "ref_id": "drv_input",
            "role": "primary",
            "selector": None,
        }
    ]
    assert document["output"]["sha256"] == "f" * 64


@pytest.mark.parametrize(
    ("operation", "determinism_class"),
    [("canonical.rewrite", "D1"), ("canonical.promote", "D9")],
)
def test_an_undeclared_operation_or_class_is_refused(db, operation, determinism_class):
    with pytest.raises(ValueError, match="declared"):
        build_recipe(db, operation, determinism_class=determinism_class, **CLOSURE)


def test_a_derivation_can_cite_the_recipe_it_was_built_from(db, lineage_env):
    seed_manifest(db, sha256="e" * 64)
    recipe_id = build_recipe(db, "canonical.promote", **CLOSURE)
    environment = lineage_env.model_copy(update={"recipe_id": recipe_id})

    with lineage_session(recorder=PostgresRecorder(db), environment=environment), derive(
        "canonical.promote",
        output=OutputSpec(store="postgres", dataset="canonical.production_monthly"),
        params={"month_convention": "production_month"},
    ) as context:
        context.set_output_hash("f" * 64)
    db.commit()

    with db.cursor() as cursor:
        cursor.execute(
            "select recipe_id from lineage.derivations where derivation_id = %s",
            (context.derivation_id,),
        )
        assert cursor.fetchone()[0] == recipe_id
