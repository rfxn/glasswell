# TX RRC PDQ fixtures — what they are, and what they are not

**Built, not cut.** Every other fixture directory here holds rows a regulator published,
sampled from a file this repository fetched. These do not, and the difference is stated first
because a count taken from a fixture is a claim about the fixture.

`PDQ_DSV.zip` is 3.65 GB behind a GoAnywhere postback that ignores `Range`, so there is no
partial fetch: the archive is acquired once, on the deployed host, through
`docs/runbook-tx-load.md`, and no development worktree holds a copy. These two archives are
therefore **constructed** by `build_fixtures.py` to the published format and dictionary, with
rows chosen to exercise the cases `cr_tx_allocation_v0_1` decides.

## What was measured live, and where

| Fact | How | Measured |
|---|---|---|
| Manual reachable, `content-length: 488959`, `last-modified: Tue, 02 Jun 2026 17:35:19 GMT`, `HTTP/2 200` | `curl -sSI https://www.rrc.texas.gov/media/50ypu2cg/pdq-dump-user-manual.pdf` | 2026-09-03T00:24:07Z |
| `sha256(pdq-dump-user-manual.pdf) = a24a6b5e5daf9863b82b579924b485de573b94e0d2da439695b72e8b04fbf4d2` | `curl -o` then `sha256sum` | 2026-09-03T00:24Z |
| Every column name, order, nullability and width below | `pdftotext -layout`, the manual's Column Definition and Data Dictionary sections | 2026-09-03 |
| The dump's own address, size and cadence | not re-measured here; P2 measures it live at its start | — |

**The `OG_LEASE_CYCLE` grain question (N-31) is answered from the regulator's own dictionary,
not from these files.** The manual declares `FIELD_NO` **nullable** on `OG_LEASE_CYCLE`, and a
nullable column does not key a table; the not-null columns are `OIL_GAS_CODE`, `DISTRICT_NO`,
`LEASE_NO`, `CYCLE_YEAR`, `CYCLE_MONTH`, `CYCLE_YEAR_MONTH` and `LEASE_NO_DISTRICT_NO`, the
last three of which are derivable from the first four. The table description reads *"Contains
production report data reported by lease and month (YYYYMM)"*, and `OG_FIELD_CYCLE` exists
separately *"aggregated by the field in which the well(s) for the lease are completed"* — which
would be redundant if the lease table were already split by field. So the key is
`(OIL_GAS_CODE, DISTRICT_NO, LEASE_NO, CYCLE_YEAR_MONTH)` and `FIELD_NO` does not split it.
These fixtures assert that premise rather than proving it; **P2 re-confirms it at full scale on
the real member**, and if it is wrong there, `field_no` joins both mart primary keys in a new
migration rather than as an edit to an applied one.

## The two archives

| Archive | Bytes | sha256 |
|---|---|---|
| `PDQ_DSV_sample.zip` | 61924 | `f2e8f964fdbdf8ae5179d2b12a0542a5122c12936debfdcac29cdef9e69dd941` |
| `PDQ_DSV_sample_restated.zip` | 61925 | `0e4b2ae5c8b9c5233cefb894f5de84f0491583f9cc8a28013ba1c9efcf77a0f2` |

Two vintages, because a restatement is two dumps: PDQ is a full monthly re-publication, so the
proof that a revised volume appends rather than edits needs the same lease-month filed twice.
Lease `O-08-000101`'s 2024-01 oil volume is 901 in the first and 1201 in the second, and
nothing else moves.

Six members each, `}`-delimited, one header row, no enclosure, deflate:

| Member | Rows | Why it is here |
|---|---|---|
| `GP_COUNTY_DATA_TABLE.dsv` | 3 | Two in-scope Permian counties and one outside them |
| `GP_DATE_RANGE_CYCLE_DATA_TABLE.dsv` | 1 | The window and the extract dates, in the five-column shape the manual declares |
| `GP_DISTRICT_DATA_TABLE.dsv` | 15 | The district trap: `07}6E`, `08}7B`, `09}7C`, `10}08`, `11}8A`, `13}09`, `14}10`, `20}State Wide` — two vocabularies in one file |
| `OG_LEASE_CYCLE_DATA_TABLE.dsv` | 12,120 over **1,000 leases** | The production grain |
| `OG_WELL_COMPLETION_DATA_TABLE.dsv` | 1,000 | The in-dump crosswalk |
| `OG_REGULATORY_LEASE_DW_DATA_TABLE.dsv` | 1,000 | The lease dimension |

## The cases the rows carry

| Lease | Case |
|---|---|
| `O-08-000101` | Multi-well oil lease, three wells; 900 divides exactly and 901 leaves the remainder that must go to the lowest API-10. Its 2024-01 volume is the restated one |
| `G-08-000202` | Gas lease, one gas well, condensate and gas-well gas — passed through `observed_gas_well` |
| `G-08-000303` | The dual-lease wellbore: API `4200300001` is on oil lease `000101` **and** on this gas lease, so one API-10 carries two lease keys in one dump |
| `O-08-000404` | Two wells, one carrying a filed plug date mid-history — `excluded_after_plug` and the redistribution that keeps V-1 exact |
| `O-08-000505` | Two wells, one flagged plugged with **no** date — stays eligible, labelled `allocated_after_status_change` |
| `O-08-000606` | A negative correction: `V = -7, n = 2` |
| `O-08-000707` | Volume filed with no crosswalk row at all — the `no_eligible_well` ledger cause |
| `O-08-000808` | Filed zeros and unfiled months, which `reported_zero` and `no_report` must keep apart |
| `O-08-000909` | Every well outside the 55-county scope — counted at promotion, never quarantined |
| `O-08-001010` | A volume that is not a number, and one that overflows `numeric(18,3)` — both `impossible_volume` |
| `O-08-002000`…`O-08-002989` | 990 single-well oil leases over twelve months, so the key question is asked of a population |

Rebuild with:

    python tests/fixtures/tx_pdq/build_fixtures.py

The build is deterministic: member timestamps are fixed, so a diff on an archive means the data
moved rather than the clock did.
