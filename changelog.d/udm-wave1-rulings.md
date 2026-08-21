- [New] `pattern` is a fact kind in `tests/contract/openapi_diff.py`, emitted per parameter
      and per schema property and through `anyOf` branches, so a relaxed identifier grammar
      is reported as the old constraint leaving rather than passing the freeze gate with no
      fact at all (UDM-SPEC §5.3 ground one, closed as a class)
- [New] Contract test pinning `API10_PATTERN` to `^\d{10}$`, that every served `{api10}`
      path declares that grammar rather than one of its own, and that a 16-character UWI is
      refused by the United States path instead of answered (UDM-SPEC §5.3, risk R-2)
- [New] Client test pinning the wells dataset's `row_id` to `["/api10"]`, with the
      counterfactual that makes the reason travel: at `["/well_id"]` every derived api10 hop
      in the explorer dies at once (UDM-SPEC §6.4, risk R-3)
- [New] Integration measurement of API-10 permanence: no well answers to two api10s and no
      api10 answers to two wells across vintages, reported with the offending api10 and the
      vintages it was seen at, and with the rows the check cannot speak for counted rather
      than hidden — §4.3(d) is an observation about ingested vintages, not a property PPDM
      certifies
- [Change] The search type guard reads the general key `(authority, native_id)` and its
           other surfaced names, so a well with no API-10 is no longer dropped silently; a
           result's `api10` is null rather than carrying a non-API-10, and the label falls
           back to the identifier the well does answer to instead of rendering `undefined`
- [Change] The explorer grid classifies `well_id`, `native_id`, `authority` and `uwi` as
           identifier columns, so the general key renders as identity rather than as prose
- [Fix] A row whose `api10` was an empty string passed the search type guard and rendered a
      blank option in the dropdown
