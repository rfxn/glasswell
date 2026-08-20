# Security Policy

## Scope

glasswell is a single-operator analytical system that runs on one VM against
public regulator files. It holds no customer data, no credentials for third-party
accounts, and no personally identifying information beyond what the states already
publish in their own filings.

In scope:

- The HTTP API and the agent gateway — injection, path traversal, unbounded
  resource consumption, and anything that lets a caller read outside the served
  surface.
- The ingest path — parser handling of hostile or malformed regulator files,
  archive extraction, and temp-file handling.
- Any code that shells out, writes to disk, or constructs SQL.

Out of scope:

- The accuracy of a forecast, a valuation, or an allocation. Those are correctness
  bugs — open a normal issue.
- Denial of service against the public source agencies. Do not test that; ingest is
  rate-limited and cached by design.
- Third-party runtimes and libraries — report those upstream.

## Supported versions

Pre-build. Once releases are tagged, only the latest tagged release receives
security fixes.

## Reporting a vulnerability

**Do not open a public issue for a security report.**

Email **ryan@rfxn.com** with:

- A description of the issue and the affected file or endpoint
- Reproduction steps or a proof of concept
- The version or commit hash you tested against

You will receive an acknowledgement within 72 hours. Fixes for confirmed issues
ship in the next tagged release, with credit in the changelog unless you ask
otherwise.

## Data handling note

Everything glasswell ingests is already public. Nothing in the raw zone is
confidential, and the manifest that records each file is designed to be published.
If a source agency ever ships something that should not have been public, the
correct response is to report it to that agency and quarantine the file here — not
to silently drop it, which would break reproducibility without fixing anything.
