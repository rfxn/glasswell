# Contract tier

FastAPI TestClient tests against the OpenAPI surface, including `/explain` chain
resolution and the naked-number harness (SB-07 §10).

`openapi_snapshot.json` is generated and never hand-edited: `make snapshot` rewrites it
(`scripts/regen-snapshot.py` takes an optional target path and a `--check` arm that reports
drift without writing). `test_regen_snapshot.py` holds that script to the same bytes the
byte-equality gate demands, so there is one regeneration path rather than one per agent.
