from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from glasswell.ingest.tx_mft import (
    OFFERED_PAGE_SIZES,
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

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tx_gis"
PAGE = FIXTURES / "mft_listing.html"
PARTIAL = FIXTURES / "mft_listing_partial.xml"
LINK = "https://mft.rrc.texas.gov/link/d551fb20-442e-4b67-84fa-ac3f23ecabb4"


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
