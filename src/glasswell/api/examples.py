"""The documented request examples, which are also the naked-number harness's input set.

SB-07 §10 check 1 fails an operation with no example, and check 2 calls every operation
with the example it publishes. So the example ids are written down once, here, and the
contract fixture seeds exactly them.

SB-08 A-1's browsable-dataset declaration lives here for the same reason: the explorer's
catalogue is generated from the served document, so the document is where the declaration has
to be right, and `dataset()` is the one place a declaration is built. A-8's per-parameter
semantics ride in the same document for the same reason.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

KEY_HEADER = "X-Glasswell-Key"
REQUEST_EXAMPLE_KEY = "x-glasswell-request-example"
GLOSSARY_KEY = "x-glasswell-glossary"
DATASET_KEY = "x-glasswell-dataset"
NOT_A_FIGURE_KEY = "x-glasswell-not-a-figure"
SEMANTICS_KEY = "x-glasswell-semantics"

DATASET_GROUPS = ("wells", "kitchen", "vocabulary", "service")
# The explorer's own top-level routes. A dataset taking one of these ids shadows the shell.
RESERVED_DATASET_IDS = frozenset({"map", "query", "learn", "api"})

Pointer = Annotated[str, Field(pattern=r"^/[^/]+(/[^/]+)*$")]
TermId = Annotated[str, Field(pattern=r"^gt_[a-z0-9_]+$")]

EXAMPLE_API10 = "3305310451"
# A box around the fixture's ND surface hole and lateral, so the published example returns a
# populated summary rather than an empty one (MAJOR-2(b): an example that resolves nowhere).
EXAMPLE_BBOX = "-104,47.5,-103,48.5"
EXAMPLE_MANIFEST_ID = "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
EXAMPLE_DERIVATION_ID = "drv_obqajdni25f25zmxcz7a"

CONTENT_ADDRESS_NOTE = (
    " The example id is the contract fixture's. `drv_`, `man_`, `qr_` and `p3pub_` ids are"
    " content addresses over bytes and run parameters, so they differ per deployment by"
    " construction — take a live one from the `d` handle on any served figure, from"
    " `/v1/manifests`, or from `/v1/modeling/publications`."
)
VINTAGE_ID_NOTE = (
    " The example id is the contract fixture's. A vintage id is `vin_<source_id>_<date>`,"
    " where the date is a knowledge date this deployment actually promoted — it is composed,"
    " not addressed, so list `/v1/vintages` and take one rather than building it."
)
EXAMPLE_RULE_ID = "cr_nd_stream_vocab_1"
EXAMPLE_SOURCE_ID = "nd_mpr_xlsx"
EXAMPLE_VINTAGE_ID = "vin_nd_mpr_xlsx_2026-08-01"
EXAMPLE_QUARANTINE_ID = "qr_01contract0001"
EXAMPLE_PUBLICATION_ID = "p3pub_92793c448b37eade223aa4b9d156be0d"
EXAMPLE_TERM_ID = "gt_report_vintage"
EXAMPLE_ERROR_CODE = "lineage_unresolved"
EXAMPLE_TILE = {"layer": "nd_laterals", "z": 8, "x": 54, "y": 89}


def request_example(
    *, path: dict[str, Any] | None = None, query: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`openapi_extra` payload: the parameters a caller (or the harness) can replay."""
    return {REQUEST_EXAMPLE_KEY: {"path": path or {}, "query": query or {}}}


def not_a_figure(reason: str) -> dict[str, Any]:
    """`json_schema_extra` payload: SB-08 A-2's exemption, served beside the number it exempts.

    The reason is byte-equal to the `non_figure_allowlist.yml` entry that covers the property's
    response pointer — `tests/contract/test_not_a_figure.py` fails if the two ever diverge, in
    either direction. Nothing else may use this key: an extension without a covering entry is a
    number claiming an exemption the allowlist never granted.
    """
    return {NOT_A_FIGURE_KEY: reason}


class RowProjection(BaseModel):
    """SB-08 rev 3 §2.3's pivot: one element of aligned arrays becomes `axis`-many rows.

    Every pointer here is relative to `Dataset.series_pointer`, and `axis` takes no suffix —
    it is the row key, not a value, and `pm_report_vintage` does not exist.
    """

    model_config = ConfigDict(extra="forbid")

    axis: Pointer
    columns: list[Pointer] = Field(min_length=1)
    suffixes: list[Annotated[str, Field(pattern=r"^_[a-z0-9_]+$")]] = Field(default_factory=list)


class DatasetColumns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: list[Pointer] | None = None
    hidden: list[Pointer] = Field(default_factory=list)
    hidden_reason: dict[str, str] = Field(default_factory=dict)
    sort: Pointer | None = None

    @model_validator(mode="after")
    def _hidden_columns_say_why(self) -> DatasetColumns:
        if set(self.hidden) != set(self.hidden_reason):
            raise ValueError(
                "columns.hidden and columns.hidden_reason must name the same pointers;"
                f" hidden={sorted(self.hidden)} hidden_reason={sorted(self.hidden_reason)}"
            )
        return self


class Dataset(BaseModel):
    """SB-08 A-1: an operation declaring itself browsable, and how to read it as rows."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    title: str
    group: Literal["wells", "kitchen", "vocabulary", "service"]
    collection_pointer: Annotated[str, Field(pattern=r"^$|^/[^/]+(/[^/]+)*$")] = ""
    series_pointer: Pointer | None = None
    row_projection: RowProjection | None = None
    anchors: list[Pointer] = Field(default_factory=list)
    row_id: list[Pointer] = Field(min_length=1)
    detail_operation: str | None = None
    summary_operation: str | None = None
    facets: list[str] = Field(default_factory=list)
    columns: DatasetColumns = Field(default_factory=DatasetColumns)
    intro: Annotated[str, Field(pattern=r"^nb_[a-z0-9_]+$")]
    order: int

    @model_validator(mode="after")
    def _the_shell_keeps_its_own_ids(self) -> Dataset:
        if self.id in RESERVED_DATASET_IDS:
            raise ValueError(f"id {self.id!r} is reserved for a shell route")
        if (self.row_projection is None) != (self.series_pointer is None):
            raise ValueError("row_projection and series_pointer are declared together or not")
        return self


def dataset(**fields: Any) -> dict[str, Any]:
    """`openapi_extra` payload: SB-08 A-1's browsable-dataset declaration.

    `exclude_none` keeps the served document to what the author wrote, so an absent
    `summary_operation` is absent rather than `null` and §2.3's schema-order fallback stays
    expressible as an omitted `columns.default`.
    """
    return {DATASET_KEY: Dataset(**fields).model_dump(exclude_none=True)}


class ParameterSemantics(BaseModel):
    """SB-08 rev 3 §4.3: one parameter's WHY source and its per-operation consequence.

    The inner member is spelled `x-glasswell-glossary` and not `glossary` because the name is
    the mechanism: `test_glossary_coverage._bindings` collects by key, at any depth, so this
    spelling puts A-8's term references under R9 with no second code path (G-2).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    glossary: TermId | None = Field(default=None, alias=GLOSSARY_KEY)
    so: Annotated[str, Field(min_length=1)] | None = None

    @model_validator(mode="after")
    def _an_entry_carries_at_least_one_of_the_two(self) -> ParameterSemantics:
        if self.glossary is None and (self.so is None or not self.so.strip()):
            raise ValueError("an entry binds a term, states a consequence, or is not written")
        return self


def semantics(**parameters: Any) -> dict[str, Any]:
    """`openapi_extra` payload: SB-08 A-8's per-parameter semantics, keyed by parameter name.

    A parameter whose OpenAPI name is a Python keyword — `from` on the production window — is
    passed by unpacking a literal mapping at the call site.
    """
    return {
        SEMANTICS_KEY: {
            name: ParameterSemantics(**entry).model_dump(by_alias=True, exclude_none=True)
            for name, entry in parameters.items()
        }
    }
