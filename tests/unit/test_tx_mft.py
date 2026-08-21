from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from glasswell.ingest.tx_mft import (
    LISTING_PAGE_ROWS,
    OFFERED_PAGE_SIZES,
    ListingError,
    ListingIncomplete,
    MftListing,
    UnknownEntry,
    apply_page,
    artifact_url,
    download_form,
    entry_name_from_url,
    fetch_listing,
    listing_page_request,
    parse_listing,
)
from glasswell.seed.conformance_tx import TX_RULES

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tx_gis"
PAGE = FIXTURES / "mft_listing.html"
PARTIAL = FIXTURES / "mft_listing_partial.xml"
LINK = "https://mft.rrc.texas.gov/link/d551fb20-442e-4b67-84fa-ac3f23ecabb4"


def _partial_of(page: str) -> str:
    """The page's own rows wrapped as a PrimeFaces partial — a portal that never advances."""
    rows = "".join(re.findall(r'<tr data-ri="\d+".*?</tr>', page, re.DOTALL))
    return (
        '<?xml version="1.0" encoding="UTF-8"?><partial-response><changes>'
        f'<update id="fileTable"><![CDATA[{rows}]]></update></changes></partial-response>'
    )


@pytest.fixture
def page() -> MftListing:
    return parse_listing(PAGE.read_text(encoding="utf-8"), link_url=LINK)


@pytest.fixture
def listing(page: MftListing) -> MftListing:
    return apply_page(page, PARTIAL.read_text(encoding="utf-8"))


def test_the_rendered_page_is_short_of_the_row_count_it_declares(page: MftListing) -> None:
    """The live folder is 255 archives behind a 250-row page; the fixture keeps that shape."""
    assert len(page.entries) < page.declared_count


def test_the_partial_completes_the_listing_and_refreshes_the_view_state(
    page: MftListing, listing: MftListing
) -> None:
    assert len(listing.entries) == listing.declared_count
    assert "well501.zip" in listing.names
    assert "well501.zip" not in page.names


def test_a_partial_that_is_still_short_is_a_failure_not_a_shorter_answer(
    page: MftListing,
) -> None:
    partial = PARTIAL.read_text(encoding="utf-8")
    rows = re.findall(r'<tr data-ri="\d+".*?</tr>', partial, re.DOTALL)
    trimmed = partial.replace(rows[-1], "")
    with pytest.raises(ListingIncomplete) as raised:
        apply_page(page, trimmed)
    assert str(page.declared_count) in str(raised.value)


def test_the_listing_hash_changes_when_the_portal_changes(page: MftListing) -> None:
    other = parse_listing(
        PAGE.read_text(encoding="utf-8").replace("well003.zip", "well004.zip"), link_url=LINK
    )
    assert page.listing_sha256 != other.listing_sha256
    assert len(page.listing_sha256) == 64


def test_the_listing_records_what_a_rotated_guid_would_change(listing: MftListing) -> None:
    provenance = listing.provenance()
    assert provenance["link_url"] == LINK
    assert provenance["entry_count"] == provenance["declared_count"]
    assert provenance["listing_sha256"] == listing.listing_sha256


def test_the_download_form_carries_the_row_id_and_the_form_submit_marker(
    listing: MftListing,
) -> None:
    form = download_form(listing, "well003.zip")
    entry = listing.entry("well003.zip")
    assert form["fileList_SUBMIT"] == "1"
    assert form["javax.faces.ViewState"] == listing.view_state
    assert form[entry.row_id] == entry.row_id


def test_an_entry_the_portal_does_not_list_is_refused_by_name(listing: MftListing) -> None:
    with pytest.raises(UnknownEntry) as raised:
        download_form(listing, "well999.zip")
    assert "well999.zip" in str(raised.value)


def test_the_artifact_url_round_trips_the_entry_name() -> None:
    url = artifact_url(LINK, "well003.zip")
    assert url.startswith(LINK)
    assert entry_name_from_url(httpx.URL(url)) == "well003.zip"


def test_the_listing_page_request_asks_for_more_rows_than_the_portal_caps_at(
    page: MftListing,
) -> None:
    body = listing_page_request(page.view_state)
    assert int(body["fileTable_rows"]) > 250
    # The portal answers a size outside its own control with IllegalArgumentException, so the
    # value has to be one it offers rather than one large enough to end the paging.
    assert int(body["fileTable_rows"]) in OFFERED_PAGE_SIZES
    assert body["javax.faces.partial.ajax"] == "true"
    assert listing_page_request(page.view_state, 1000)["fileTable_first"] == "1000"


def test_fetch_listing_refuses_a_folder_that_never_completes() -> None:
    """The guard on the path production actually runs.

    `apply_page` has no production caller — `MftClient` goes through `fetch_listing` — so the
    completeness assertion was only ever exercised on a helper the shipping code never calls,
    and deleting the real one left the suite green. This drives the real one: a portal that
    ignores `fileTable_first` answers every page with the same rows, so the loop stops making
    progress and the folder is still short of the count the page declared.
    """
    page = PAGE.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=page)
        # Same first page every time, whatever offset was asked for.
        return httpx.Response(200, text=_partial_of(page))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ListingIncomplete) as raised:
            fetch_listing(client, LINK)
    assert "declares" in str(raised.value)


def test_fetch_listing_refuses_a_page_size_the_portal_rejects() -> None:
    """The live portal answers an unoffered size with IllegalArgumentException, not a page."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=PAGE.read_text(encoding="utf-8"))
        return httpx.Response(
            200,
            text='<?xml version="1.0"?><partial-response><error><error-name>'
            "java.lang.IllegalArgumentException</error-name><error-message><![CDATA["
            "Unsupported rows per page value: 5000]]></error-message></error></partial-response>",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ListingError, match="Unsupported rows per page"):
            fetch_listing(client, LINK)


def test_the_page_size_the_rule_records_is_the_one_the_code_asks_for() -> None:
    """R8: the registry row is the served record of the acquisition decision, so a rule that
    named 5,000 documented a request the portal refuses."""
    declared = next(
        row for row in TX_RULES if row["rule_id"] == "cr_tx_mft_resolve_1"
    )["spec"]["listing_page_rows"]

    assert declared == LISTING_PAGE_ROWS
    assert declared in OFFERED_PAGE_SIZES


def test_fetch_listing_pages_once_and_only_when_the_page_is_short() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, text=PAGE.read_text(encoding="utf-8"))
        return httpx.Response(200, text=PARTIAL.read_text(encoding="utf-8"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        listing = fetch_listing(client, LINK)
    assert calls == ["GET", "POST"]
    assert len(listing.entries) == listing.declared_count
