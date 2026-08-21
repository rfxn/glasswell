"""SB-08 A-1: `x-glasswell-dataset`, and the lint that keeps a generated catalogue honest.

The explorer's rail is built from this extension rather than from a list in the client
(SB-08 §2.3), so a declaration naming a missing operation or an unresolvable pointer is a rail
entry pointing at nothing. Every rule is checked against the served document and then against a
mutant that breaks it: a lint whose failure path is never taken is a comment.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from glasswell.api.examples import (
    DATASET_GROUPS,
    DATASET_KEY,
    RESERVED_DATASET_IDS,
    dataset,
)

MIN_DEFAULT_COLUMNS = 5
MAX_DEFAULT_COLUMNS = 7
MAX_REF_HOPS = 8


def declarations(
    document: dict[str, Any],
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Every operation that declares itself browsable, with its declaration and itself."""
    return [
        (operation["operationId"], operation[DATASET_KEY], operation)
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and DATASET_KEY in operation
    ]


def operation_ids(document: dict[str, Any]) -> set[str]:
    return {
        operation["operationId"]
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }


def _deref(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    for _ in range(MAX_REF_HOPS):
        if "$ref" not in schema:
            return schema
        schema = document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    raise AssertionError(f"$ref chain deeper than {MAX_REF_HOPS} hops")


def _object(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Follow `$ref`, then unwrap pydantic's nullable `anyOf` to the branch that carries shape."""
    schema = _deref(document, schema)
    if "properties" in schema or "items" in schema:
        return schema
    for key in ("anyOf", "oneOf", "allOf"):
        for branch in schema.get(key, ()):
            candidate = _deref(document, branch)
            if "properties" in candidate or "items" in candidate:
                return candidate
    return schema


def _element(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """The row-bearing schema: an array's items, or the schema itself."""
    schema = _object(document, schema)
    if schema.get("type") == "array":
        return _object(document, schema["items"])
    return schema


def _at(
    document: dict[str, Any], schema: dict[str, Any], pointer: str
) -> dict[str, Any] | None:
    """The schema a JSON Pointer names, descending arrays transparently; None when absent."""
    node = schema
    for segment in pointer.split("/")[1:]:
        child = _element(document, node).get("properties", {}).get(segment)
        if child is None:
            return None
        node = child
    return node


def _is_array(document: dict[str, Any], schema: dict[str, Any]) -> bool:
    return _object(document, schema).get("type") == "array"


def _distinct(*spaces: dict[str, Any] | None) -> list[dict[str, Any]]:
    seen: dict[int, dict[str, Any]] = {}
    for space in spaces:
        if space is not None:
            seen.setdefault(id(space), space)
    return list(seen.values())


def _pointer_findings(
    document: dict[str, Any],
    operation_id: str,
    declaration: dict[str, Any],
    operation: dict[str, Any],
) -> list[str]:
    """A-1 rule 3: every pointer resolves in the operation's own response schema."""
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    envelope = _object(document, schema)
    root = _element(document, envelope["properties"]["data"])

    collection = declaration.get("collection_pointer", "")
    found = _at(document, root, collection)
    if found is None:
        return [f"{operation_id}: collection_pointer {collection} does not resolve"]
    if collection and not _is_array(document, found):
        return [f"{operation_id}: collection_pointer {collection} is not an array"]
    element = _element(document, found)

    series = None
    series_pointer = declaration.get("series_pointer")
    if series_pointer is not None:
        found = _at(document, element, series_pointer)
        if found is None:
            return [f"{operation_id}: series_pointer {series_pointer} does not resolve"]
        series = _element(document, found)

    # A projected row spans three namespaces and they are not interchangeable: the root and the
    # element carry the scalars that sit beside the array, the series carries the aligned
    # columns. `anchors[]` is the first pair only — a series column is not a row anchor.
    anchor_space = _distinct(root, element)
    row_space = _distinct(root, element, series)

    def missing(pointer: str, spaces: list[dict[str, Any]]) -> bool:
        return all(_at(document, space, pointer) is None for space in spaces)

    findings: list[str] = []
    columns = declaration.get("columns", {})
    for member, pointers, spaces in (
        ("row_id", declaration.get("row_id", []), row_space),
        ("columns.default", columns.get("default") or [], row_space),
        ("columns.hidden", columns.get("hidden", []), row_space),
        ("anchors", declaration.get("anchors", []), anchor_space),
    ):
        findings += [
            f"{operation_id}: {member} pointer {pointer} does not resolve"
            for pointer in pointers
            if missing(pointer, spaces)
        ]

    sort = columns.get("sort")
    if sort is not None and missing(sort, row_space):
        findings.append(f"{operation_id}: columns.sort pointer {sort} does not resolve")

    projection = declaration.get("row_projection")
    if projection is None:
        if series is not None:
            findings.append(
                f"{operation_id}: series_pointer {series_pointer} declares no row_projection"
            )
        return findings
    if series is None:
        return [*findings, f"{operation_id}: row_projection declares no series_pointer"]

    axis = projection["axis"]
    axis_schema = _at(document, series, axis)
    if axis_schema is None:
        findings.append(f"{operation_id}: row_projection.axis {axis} does not resolve")
    elif not _is_array(document, axis_schema):
        # The axis is the row count, so a scalar there projects an unknowable number of rows.
        findings.append(f"{operation_id}: row_projection.axis {axis} is not an array")
    suffixes = projection.get("suffixes", [])
    for pointer in projection.get("columns", []):
        if missing(pointer, [series]):
            findings.append(f"{operation_id}: row_projection column {pointer} does not resolve")
            continue
        findings += [
            f"{operation_id}: row_projection column {pointer} has no {suffix} companion"
            for suffix in suffixes
            if missing(f"{pointer}{suffix}", [series])
        ]
    return findings


def dataset_findings(document: dict[str, Any]) -> list[str]:
    """Every way an A-1 declaration can be wrong, stated once, checkable against any document."""
    findings: list[str] = []
    known = operation_ids(document)
    claimed_ids: dict[str, str] = {}
    claimed_orders: dict[int, str] = {}

    for operation_id, declaration, operation in declarations(document):
        dataset_id = declaration.get("id")
        if dataset_id in RESERVED_DATASET_IDS:
            findings.append(f"{operation_id}: id {dataset_id!r} is reserved for a shell route")
        if dataset_id in claimed_ids:
            findings.append(f"{operation_id}: id {dataset_id!r} is also {claimed_ids[dataset_id]}")
        claimed_ids[str(dataset_id)] = operation_id

        order = declaration.get("order")
        if order in claimed_orders:
            findings.append(f"{operation_id}: order {order} collides with {claimed_orders[order]}")
        claimed_orders[order] = operation_id

        group = declaration.get("group")
        if group not in DATASET_GROUPS:
            findings.append(f"{operation_id}: group {group!r} is not one of {DATASET_GROUPS}")

        findings += [
            f"{operation_id}: {member} {declaration[member]!r} is not an operation here"
            for member in ("detail_operation", "summary_operation")
            if declaration.get(member) is not None and declaration[member] not in known
        ]

        queries = {
            parameter["name"]
            for parameter in operation.get("parameters", [])
            if parameter["in"] == "query"
        }
        findings += [
            f"{operation_id}: facet {facet!r} is not a query parameter"
            for facet in declaration.get("facets", [])
            if facet not in queries
        ]

        # A path parameter is not a filter the grid can append: it narrows the URL itself, so a
        # dataset behind one is unbrowsable until the reader supplies it. Declaring it as an
        # anchor is what lets the rail say so instead of letting the UI discover a 404.
        anchored = set(declaration.get("anchors", []))
        findings += [
            f"{operation_id}: path parameter {parameter['name']!r} is not an anchor"
            for parameter in operation.get("parameters", [])
            if parameter["in"] == "path"
            and parameter.get("required", False)
            and f"/{parameter['name']}" not in anchored
        ]

        columns = declaration.get("columns", {})
        hidden = set(columns.get("hidden", []))
        reasons = set(columns.get("hidden_reason", {}))
        findings += [
            f"{operation_id}: hidden {pointer} carries no hidden_reason"
            for pointer in sorted(hidden - reasons)
        ]
        findings += [
            f"{operation_id}: hidden_reason {pointer} is not hidden"
            for pointer in sorted(reasons - hidden)
        ]

        findings += _pointer_findings(document, operation_id, declaration, operation)
    return findings


@pytest.fixture
def document(client: TestClient) -> dict[str, Any]:
    return client.get("/openapi.json").json()


def _declaration(document: dict[str, Any], operation_id: str) -> dict[str, Any]:
    for declared_id, declaration, _ in declarations(document):
        if declared_id == operation_id:
            return copy.deepcopy(declaration)
    raise AssertionError(f"{operation_id} declares no dataset")


def _mutated(
    document: dict[str, Any], operation_id: str, declaration: dict[str, Any] | None
) -> dict[str, Any]:
    """A deep copy of the served document carrying one altered (or added) declaration."""
    mutant = copy.deepcopy(document)
    for item in mutant["paths"].values():
        for operation in item.values():
            if isinstance(operation, dict) and operation.get("operationId") == operation_id:
                if declaration is None:
                    operation.pop(DATASET_KEY, None)
                else:
                    operation[DATASET_KEY] = declaration
    return mutant


def _pivot() -> dict[str, Any]:
    """The rev-3 pivot shape, against the schema C2 will declare it on."""
    return {
        "id": "production",
        "title": "Production",
        "group": "wells",
        "collection_pointer": "",
        "series_pointer": "/series",
        "row_projection": {
            "axis": "/pm",
            "columns": ["/oil_bbl", "/gas_mcf", "/water_bbl"],
            "suffixes": ["_report_vintage", "_null_semantics", "_aggregation"],
        },
        "anchors": ["/api10", "/granularity", "/reporting_level"],
        "row_id": ["/pm"],
        "facets": ["stream", "from", "to"],
        "columns": {
            "default": ["/pm", "/oil_bbl", "/gas_mcf", "/water_bbl", "/granularity"],
            "hidden": [],
            "hidden_reason": {},
        },
        "intro": "nb_dataset_production",
        "order": 11,
    }


def _projection() -> dict[str, Any]:
    """The rev-3 projection shape: the browsable array is a property of `data`, not `data`."""
    return {
        "id": "sources",
        "title": "Sources & freshness",
        "group": "service",
        "collection_pointer": "/sources",
        "row_id": ["/source_id"],
        "columns": {
            "default": [
                "/source_id",
                "/name",
                "/state",
                "/retrieval_vintage",
                "/declared_vintage",
                "/manifest_count",
            ],
        },
        "intro": "nb_dataset_sources",
        "order": 50,
    }


def test_the_served_datasets_pass_the_lint(document: dict[str, Any]) -> None:
    """The gate itself. `declared` guards the vacuous pass an empty document would give."""
    declared = declarations(document)

    assert declared, "no operation declares itself browsable"
    assert dataset_findings(document) == []


def test_every_declared_dataset_carries_an_explicit_default_column_list(
    document: dict[str, Any],
) -> None:
    """SB-08 rev 3: `columns.default` is the binding ratchet's denominator, so it is a phase
    gate rather than presentation — a reviewable list, not an emergent property of a fallback."""
    sized = {
        operation_id: len((declaration.get("columns") or {}).get("default") or [])
        for operation_id, declaration, _ in declarations(document)
    }

    assert sized
    assert {
        operation_id: size
        for operation_id, size in sized.items()
        if not MIN_DEFAULT_COLUMNS <= size <= MAX_DEFAULT_COLUMNS
    } == {}


def test_a_dataset_may_omit_its_default_columns(document: dict[str, Any]) -> None:
    """§2.3's fallback — every property in schema order — stays legal in the grammar, so the
    client's fallback path is specified rather than dead. No P-A dataset takes it."""
    declaration = _declaration(document, "list_wells")
    declaration["columns"].pop("default")

    assert dataset_findings(_mutated(document, "list_wells", declaration)) == []


def test_a_detail_operation_that_does_not_exist_fails_the_lint(
    document: dict[str, Any],
) -> None:
    """SB-08 §9's drift test by name: a dead rail entry is a lint failure, not a rendered link."""
    declaration = _declaration(document, "list_wells") | {"detail_operation": "get_nothing"}

    findings = dataset_findings(_mutated(document, "list_wells", declaration))

    assert findings == ["list_wells: detail_operation 'get_nothing' is not an operation here"]


def test_a_reserved_id_fails_the_lint(document: dict[str, Any]) -> None:
    """`map`, `query`, `learn` and `api` are shell routes; a dataset taking one shadows it."""
    for reserved in sorted(RESERVED_DATASET_IDS):
        declaration = _declaration(document, "list_wells") | {"id": reserved}

        findings = dataset_findings(_mutated(document, "list_wells", declaration))

        assert findings == [f"list_wells: id {reserved!r} is reserved for a shell route"]


def test_two_datasets_may_not_claim_one_id(document: dict[str, Any]) -> None:
    declaration = _declaration(document, "list_quarantine") | {"id": "wells"}

    findings = dataset_findings(_mutated(document, "list_quarantine", declaration))

    assert "list_quarantine: id 'wells' is also list_wells" in findings


def test_two_datasets_may_not_claim_one_rail_position(document: dict[str, Any]) -> None:
    """Duplicate `order` leaves the rail's sort undefined, which C6 renders as a flapping list."""
    order = _declaration(document, "list_wells")["order"]
    declaration = _declaration(document, "list_quarantine") | {"order": order}

    findings = dataset_findings(_mutated(document, "list_quarantine", declaration))

    assert f"list_quarantine: order {order} collides with list_wells" in findings


def test_a_group_outside_the_four_fails_the_lint(document: dict[str, Any]) -> None:
    """The rail renders four groups; a fifth would be a dataset nothing draws."""
    declaration = _declaration(document, "list_wells") | {"group": "geology"}

    findings = dataset_findings(_mutated(document, "list_wells", declaration))

    assert findings == [f"list_wells: group 'geology' is not one of {DATASET_GROUPS}"]


def test_a_default_column_pointer_that_does_not_resolve_fails_the_lint(
    document: dict[str, Any],
) -> None:
    declaration = _declaration(document, "list_wells")
    declaration["columns"]["default"] = ["/api10", "/operator_name"]

    findings = dataset_findings(_mutated(document, "list_wells", declaration))

    assert findings == ["list_wells: columns.default pointer /operator_name does not resolve"]


def test_a_row_id_pointer_that_does_not_resolve_fails_the_lint(
    document: dict[str, Any],
) -> None:
    declaration = _declaration(document, "list_conformance_rules") | {"row_id": ["/pool_id"]}

    findings = dataset_findings(_mutated(document, "list_conformance_rules", declaration))

    assert findings == ["list_conformance_rules: row_id pointer /pool_id does not resolve"]


def test_a_facet_that_is_not_a_query_parameter_fails_the_lint(
    document: dict[str, Any],
) -> None:
    """The filter set is the parameter set (§3.1); a facet with no parameter cannot be issued."""
    declaration = _declaration(document, "list_wells")
    declaration["facets"] = [*declaration["facets"], "basin"]

    findings = dataset_findings(_mutated(document, "list_wells", declaration))

    assert findings == ["list_wells: facet 'basin' is not a query parameter"]


def test_a_hidden_column_without_a_reason_fails_the_lint(document: dict[str, Any]) -> None:
    declaration = _declaration(document, "list_quarantine")
    declaration["columns"]["hidden_reason"].pop("/notes")

    findings = dataset_findings(_mutated(document, "list_quarantine", declaration))

    assert findings == ["list_quarantine: hidden /notes carries no hidden_reason"]


def test_a_series_pivot_resolves_through_its_series_pointer(document: dict[str, Any]) -> None:
    """G-1's grammar, exercised at C1 against the schema C2 declares it on: `/oil_bbl` resolves
    because `series_pointer` composes onto it, not because it sits beside `data`."""
    mutant = _mutated(document, "get_well_production", _pivot())

    assert dataset_findings(mutant) == []


def test_a_pivot_column_is_relative_to_the_series_and_not_to_the_element(
    document: dict[str, Any],
) -> None:
    """The namespace rule stated as a falsifiable claim: an element-relative spelling fails."""
    declaration = _pivot()
    declaration["row_projection"]["columns"] = ["/series/oil_bbl"]

    findings = dataset_findings(_mutated(document, "get_well_production", declaration))

    assert findings == [
        "get_well_production: row_projection column /series/oil_bbl does not resolve"
    ]


def test_the_axis_column_is_exempt_from_suffix_expansion(document: dict[str, Any]) -> None:
    """`pm` has no `pm_report_vintage`. Projected as the axis it is a key and takes no suffix;
    the same pointer moved into `columns[]` is a value and the lint demands the companions."""
    declaration = _pivot()
    declaration["row_projection"] = {
        "axis": "/oil_bbl",
        "columns": ["/pm"],
        "suffixes": ["_report_vintage"],
    }

    findings = dataset_findings(_mutated(document, "get_well_production", declaration))

    assert findings == ["get_well_production: row_projection column /pm has no _report_vintage"
                        " companion"]


def test_a_pivot_axis_that_does_not_resolve_fails_the_lint(document: dict[str, Any]) -> None:
    """The axis is the row count. An axis naming nothing projects an unknown number of rows."""
    declaration = _pivot()
    declaration["row_projection"]["axis"] = "/month"

    findings = dataset_findings(_mutated(document, "get_well_production", declaration))

    assert findings == ["get_well_production: row_projection.axis /month does not resolve"]


def test_a_pivot_through_a_collection_pointer_composes_both_prefixes(
    document: dict[str, Any],
) -> None:
    """The pooled shape C2 declares: `/pools` selects the element set, `/series` the namespace,
    and the composite row id spans both — `well_completion_pool` on the element, `pm` on the
    series. One declaration, two prefixes, no repetition."""
    declaration = _pivot() | {
        "id": "production_pools",
        "collection_pointer": "/pools",
        "row_id": ["/well_completion_pool", "/pm"],
        "facets": ["stream"],
        "order": 12,
    }

    assert dataset_findings(_mutated(document, "get_well_production_pools", declaration)) == []


def test_an_anchor_is_read_from_the_element_and_never_from_the_series(
    document: dict[str, Any],
) -> None:
    """`anchors[]` are the scalars beside the array (§2.3); a series column is not one."""
    declaration = _pivot() | {"anchors": ["/api10", "/oil_bbl"]}

    findings = dataset_findings(_mutated(document, "get_well_production", declaration))

    assert findings == ["get_well_production: anchors pointer /oil_bbl does not resolve"]


def test_a_required_path_parameter_must_be_named_as_an_anchor(
    document: dict[str, Any],
) -> None:
    """`api10` is in the path, so this dataset cannot be browsed until the reader supplies one.
    The anchor is how the rail knows that before the API answers 404 (§2.1)."""
    declaration = _pivot() | {"anchors": ["/granularity", "/reporting_level"]}

    findings = dataset_findings(_mutated(document, "get_well_production", declaration))

    assert findings == ["get_well_production: path parameter 'api10' is not an anchor"]


def test_a_series_pointer_with_no_row_projection_fails_the_lint(
    document: dict[str, Any],
) -> None:
    """A half-declared pivot is a defect rather than a default — without the projection the
    series object reads as a single row. The model refuses it at authoring time; the lint
    refuses a document that carries it anyway."""
    declaration = _pivot()
    declaration.pop("row_projection")

    findings = dataset_findings(_mutated(document, "get_well_production", declaration))

    assert findings == ["get_well_production: series_pointer /series declares no row_projection"]


def test_a_collection_pointer_that_names_no_array_fails_the_lint(
    document: dict[str, Any],
) -> None:
    """`collection_pointer` selects the element set; a scalar has no elements to browse."""
    declaration = _projection() | {"collection_pointer": "/state"}

    findings = dataset_findings(_mutated(document, "get_health", declaration))

    assert findings == ["get_health: collection_pointer /state is not an array"]


def test_a_pivot_axis_that_is_not_an_array_fails_the_lint(document: dict[str, Any]) -> None:
    """The axis's length is the row count, so a scalar axis projects an unknowable number of
    rows — the failure C7 would otherwise render as one row per character."""
    declaration = _projection() | {
        "collection_pointer": "",
        "series_pointer": "/sources",
        "row_projection": {"axis": "/manifest_count", "columns": [], "suffixes": []},
    }

    findings = dataset_findings(_mutated(document, "get_health", declaration))

    assert findings == ["get_health: row_projection.axis /manifest_count is not an array"]


def test_the_helper_refuses_a_reserved_id_at_authoring_time() -> None:
    """The document lint is the gate; the model is the fast failure, so a typo never reaches it."""
    with pytest.raises(ValidationError, match="reserved"):
        dataset(**(_pivot() | {"id": "map"}))


def test_the_helper_refuses_a_member_a_1_does_not_define() -> None:
    """A misspelled member is how a declaration silently loses its columns (B5)."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        dataset(**(_pivot() | {"column": {"default": ["/pm"]}}))


def test_the_helper_refuses_a_hidden_column_with_no_reason() -> None:
    fields = _pivot()
    fields["columns"]["hidden"] = ["/streams"]

    with pytest.raises(ValidationError, match="hidden_reason"):
        dataset(**fields)


def test_the_helper_omits_what_a_declaration_did_not_state() -> None:
    """`exclude_none` keeps the served document to what an author actually wrote — an absent
    `summary_operation` is absent, not `null`, and the fallback stays expressible."""
    fields = _pivot()
    fields["columns"].pop("default")

    payload = dataset(**fields)[DATASET_KEY]

    assert "summary_operation" not in payload
    assert "default" not in payload["columns"]
    assert payload["series_pointer"] == "/series"
