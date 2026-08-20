"""DR-67: `/v1/keys*` — owner scope, shown once, sha256 at rest, fail-closed, audited."""

from __future__ import annotations

import logging

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.access_log import ACCESS_LOGGER, install_access_log_redaction
from glasswell.api.deps import ALLOW_ANON_ENV
from glasswell.api.principal import fingerprint
from tests.contract.conftest import as_principal, issue_key

KEY_PATHS = ("/v1/keys",)


def _live_rows(connection: psycopg.Connection, statement: str) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(statement)
        return cursor.fetchall()


def test_a_key_is_issued_with_its_cleartext_exactly_once(client: TestClient) -> None:
    response = client.post("/v1/keys", json={"label": "qa-issue-2026", "scope": "guest"})

    assert response.status_code == 201
    issued = response.json()["data"]
    assert issued["secret"]
    assert issued["scope"] == "guest"
    assert issued["state"] == "active"

    listed = client.get("/v1/keys").json()["data"]
    record = next(row for row in listed if row["key_id"] == issued["key_id"])
    assert "secret" not in record
    assert client.get("/v1/keys").text.find(issued["secret"]) == -1


def test_only_the_hash_reaches_the_table(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """SB-06 §8.3: sha256 is the only representation at rest."""
    secret = issue_key(client, label="qa-at-rest-2026", scope="agent")

    stored = _live_rows(seeded, "select sha256, label from lineage.api_keys")

    assert fingerprint(secret) in {row[0] for row in stored}
    assert all(secret not in str(row) for row in stored)


def test_the_issued_key_authenticates_at_its_own_scope(client: TestClient) -> None:
    guest = as_principal(client, issue_key(client, label="qa-scope-2026", scope="guest"))

    assert guest.get("/v1/health").status_code == 200
    assert guest.get("/v1/keys").status_code == 403


def test_issuance_and_revocation_are_audit_events(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    issued = client.post("/v1/keys", json={"label": "qa-audit-2026", "scope": "agent"}).json()
    key_id = issued["data"]["key_id"]

    client.delete(f"/v1/keys/{key_id}")

    with seeded.cursor() as cursor:
        cursor.execute(
            "select event_type from lineage.audit_events"
            " where subject_id = %s order by occurred_at",
            (key_id,),
        )
        assert [row[0] for row in cursor.fetchall()] == ["key.issued", "key.revoked"]


def test_a_revoked_key_stops_working_and_says_so(client: TestClient) -> None:
    secret = issue_key(client, label="qa-revoke-2026", scope="agent")
    agent = as_principal(client, secret)
    key_id = next(
        row["key_id"] for row in client.get("/v1/keys").json()["data"]
        if row["label"] == "qa-revoke-2026"
    )
    assert agent.get("/v1/health").status_code == 200

    client.delete(f"/v1/keys/{key_id}")

    denied = agent.get("/v1/health")
    assert denied.status_code == 403
    assert denied.json()["type"].endswith("/key_revoked")


def test_revoking_twice_writes_one_event(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """A retry after a timeout must not look like a second revocation in the audit stream."""
    issued = client.post("/v1/keys", json={"label": "qa-idem-2026", "scope": "guest"}).json()
    key_id = issued["data"]["key_id"]

    first = client.delete(f"/v1/keys/{key_id}")
    second = client.delete(f"/v1/keys/{key_id}")

    assert first.status_code == second.status_code == 200
    assert second.json()["data"]["state"] == "revoked"
    with seeded.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.audit_events"
            " where subject_id = %s and event_type = 'key.revoked'",
            (key_id,),
        )
        assert cursor.fetchone()[0] == 1


def test_rotation_replaces_the_key_under_the_same_label(client: TestClient) -> None:
    old_secret = issue_key(client, label="qa-rotate-2026", scope="agent")
    old_id = next(
        row["key_id"] for row in client.get("/v1/keys").json()["data"]
        if row["label"] == "qa-rotate-2026"
    )

    rotated = client.post(f"/v1/keys/{old_id}/rotate")

    assert rotated.status_code == 201
    new_secret = rotated.json()["data"]["secret"]
    assert new_secret != old_secret
    assert as_principal(client, new_secret).get("/v1/health").status_code == 200
    assert as_principal(client, old_secret).get("/v1/health").status_code == 403


def test_a_second_live_key_cannot_take_a_label_in_use(client: TestClient) -> None:
    issue_key(client, label="qa-unique-2026", scope="guest")

    clash = client.post("/v1/keys", json={"label": "qa-unique-2026", "scope": "guest"})

    assert clash.status_code == 422
    assert clash.json()["errors"][0]["code"] == "label_in_use"


def test_an_unknown_key_and_an_empty_table_answer_identically(client: TestClient) -> None:
    """Fail-safe deny (SB-06 §8.3): no rows is not a reason to let anybody in."""
    stranger = as_principal(client, "not-a-key-that-was-ever-issued")

    denied = stranger.get("/v1/health")

    assert denied.status_code == 403
    assert denied.json()["type"].endswith("/unauthenticated")
    assert "detail" not in denied.json(), "the body must not be an oracle for why a key failed"


def test_a_dry_run_creates_nothing(client: TestClient, seeded: psycopg.Connection) -> None:
    before = _live_rows(seeded, "select key_id from lineage.api_keys")

    preview = client.post(
        "/v1/keys", params={"dry_run": "true"}, json={"label": "qa-dry-2026", "scope": "guest"}
    )

    assert preview.status_code == 200
    assert preview.json()["data"]["secret"] is None
    assert preview.json()["data"]["state"] == "not_issued"
    assert [warning["code"] for warning in preview.json()["meta"]["warnings"]] == ["dry_run"]
    assert _live_rows(seeded, "select key_id from lineage.api_keys") == before


def test_explain_and_dry_run_together_are_refused(client: TestClient) -> None:
    """S-K: the combination is the only thing rejected; either flag alone is allowed."""
    response = client.post(
        "/v1/keys",
        params={"dry_run": "true", "explain": "true"},
        json={"label": "qa-both-2026", "scope": "guest"},
    )

    assert response.status_code == 422
    assert response.json()["type"].endswith("/explain_on_dry_run")


def test_explain_alone_is_accepted_and_says_what_it_cannot_explain(client: TestClient) -> None:
    response = client.post(
        "/v1/keys", params={"explain": "true"}, json={"label": "qa-explain-2026", "scope": "guest"}
    )

    assert response.status_code == 201
    codes = [warning["code"] for warning in response.json()["meta"]["warnings"]]
    assert codes == ["explain_not_applicable"]


def test_the_cleartext_never_reaches_the_access_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The adversarial journal probe: the secret is in a response body, never a request line."""
    install_access_log_redaction()
    logger = logging.getLogger(ACCESS_LOGGER)

    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        secret = issue_key(client, label="qa-journal-2026", scope="guest")
        logger.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1", "POST", "/v1/keys", "1.1", 201)

    assert secret not in caplog.text


@pytest.mark.parametrize("path", KEY_PATHS)
def test_no_key_surface_is_reachable_without_a_credential(
    client: TestClient, path: str
) -> None:
    anonymous = as_principal(client, None)

    assert anonymous.get(path).status_code == 403
    assert anonymous.post(path, json={"label": "qa-anon-2026", "scope": "guest"}).status_code == 403


def test_the_anonymous_break_glass_cannot_mint_a_key(
    client: TestClient, seeded: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gate-a2-qa m-7: `GLASSWELL_ALLOW_ANON=1` resolves to owner *scope* with no credential
    presented, so before this guard the read break-glass reached the credential-minting
    surface and could leave durable owner keys behind that outlive the flag."""
    monkeypatch.setenv(ALLOW_ANON_ENV, "1")
    anonymous = as_principal(client, None)
    before = _live_rows(seeded, "select key_id from lineage.api_keys")

    assert anonymous.get("/v1/health").status_code == 200, "the read break-glass still reads"

    minted = anonymous.post("/v1/keys", json={"label": "qa-breakglass-2026", "scope": "owner"})
    revoked = anonymous.delete("/v1/keys/key_that_need_not_exist")

    assert minted.status_code == 403
    assert minted.json()["type"].endswith("/forbidden")
    assert revoked.status_code == 403
    assert _live_rows(seeded, "select key_id from lineage.api_keys") == before
