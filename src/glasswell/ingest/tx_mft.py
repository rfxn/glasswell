"""`mft_guid_resolve`: the RRC's GoAnywhere public links, resolved to bytes (SB-01 §1.2).

The portal is a JSF application, not a file server. A download is a form postback against a
row id that only exists inside one rendered listing, so an artifact has no stable URL and the
listing is the evidence for what was on offer at fetch time — its hash is what turns a rotated
GUID or a withdrawn county into a visible change rather than a mystery 404.

Two things here are load-bearing and were both measured against the live portal:

* the listing paginates at 250 rows while the well-layer folder holds 255, so a caller that
  reads the first page silently loses four counties. The full set is pulled with one
  PrimeFaces partial request and reconciled against the row count the page declares.
* `fetch_raw` speaks GET. The postback is expressed as an `httpx` transport rather than as a
  change to the fetch path, so the acquisition method stays a transport concern and every
  manifest, hash and derivation the raw zone writes is the same code as for `https_get`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from types import TracebackType
from urllib.parse import parse_qs, quote, urlencode

import httpx

USER_AGENT = "glasswell-ingest (+ryan@rfxn.com)"
FILENAME_PARAM = "filename"
LISTING_TIMEOUT_SECONDS = 120.0
DOWNLOAD_TIMEOUT_SECONDS = 1800.0
# The portal validates rows-per-page against its own control and answers a value outside it
# with `IllegalArgumentException: Unsupported rows per page value`, so this is the largest it
# offers rather than the largest that would be convenient. Folders larger than one page are
# read by paging, which is why the value is not load-bearing on its own.
LISTING_PAGE_ROWS = 1000
OFFERED_PAGE_SIZES = (100, 250, 500, 1000)

_ROW = re.compile(
    r'<a id="(?P<row_id>fileTable:\d+:[A-Za-z0-9_]+)"[^>]*>(?P<name>[^<]+)</a>'
    r'.*?class="ModifiedOnColumn">(?P<modified>[^<]*)</td>'
    r'.*?class="SizeColumn">(?P<size>[^<]*)</td>',
    re.DOTALL,
)
_VIEW_STATE = re.compile(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"')
_PARTIAL_VIEW_STATE = re.compile(
    r'<update id="[^"]*javax\.faces\.ViewState[^"]*"><!\[CDATA\[(.*?)\]\]></update>', re.DOTALL
)
_PARTIAL_TABLE = re.compile(r'<update id="fileTable"><!\[CDATA\[(.*?)\]\]></update>', re.DOTALL)
_PARTIAL_ERROR = re.compile(r"<error-message><!\[CDATA\[(.*?)\]\]></error-message>", re.DOTALL)
_ROW_COUNT = re.compile(r"rowCount:(\d+)")


class ListingError(RuntimeError):
    """The portal answered, but not with a listing this code can act on."""


class ListingIncomplete(ListingError):
    """Fewer rows arrived than the portal declared: a missing county, not a smaller folder."""


class UnknownEntry(LookupError):
    """The listing does not offer the artifact the caller asked for."""


@dataclass(frozen=True, slots=True)
class MftEntry:
    name: str
    row_id: str
    modified_label: str
    size_label: str


@dataclass(frozen=True, slots=True)
class MftListing:
    link_url: str
    view_state: str
    declared_count: int
    entries: tuple[MftEntry, ...]
    listing_sha256: str

    def entry(self, name: str) -> MftEntry:
        for entry in self.entries:
            if entry.name == name:
                return entry
        raise UnknownEntry(f"{name} is not offered by {self.link_url}")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(entry.name for entry in self.entries)

    def provenance(self) -> dict[str, object]:
        """What the resolution step records, so a GUID rotation is a diff and not a surprise."""
        return {
            "link_url": self.link_url,
            "listing_sha256": self.listing_sha256,
            "declared_count": self.declared_count,
            "entry_count": len(self.entries),
        }


def _entries(html: str) -> tuple[MftEntry, ...]:
    return tuple(
        MftEntry(
            name=match.group("name").strip(),
            row_id=match.group("row_id"),
            modified_label=match.group("modified").strip(),
            size_label=match.group("size").strip(),
        )
        for match in _ROW.finditer(html)
    )


def parse_listing(html: str, *, link_url: str) -> MftListing:
    """The rendered folder page: its view state, its declared row count and its first page."""
    view_state = _VIEW_STATE.search(html)
    if view_state is None:
        raise ListingError(f"{link_url} rendered no JSF view state; the portal changed shape")
    declared = _ROW_COUNT.search(html)
    if declared is None:
        raise ListingError(f"{link_url} declares no row count; completeness cannot be checked")
    entries = _entries(html)
    if not entries:
        raise ListingError(f"{link_url} lists no files")
    return MftListing(
        link_url=link_url,
        view_state=view_state.group(1),
        declared_count=int(declared.group(1)),
        entries=entries,
        listing_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
    )


def page_entries(partial: str, link_url: str) -> tuple[tuple[MftEntry, ...], str | None]:
    """The rows and the refreshed view state one partial response carries."""
    table = _PARTIAL_TABLE.search(partial)
    if table is None:
        error = _PARTIAL_ERROR.search(partial)
        detail = error.group(1).strip() if error else "no fileTable update"
        raise ListingError(f"{link_url} returned {detail}")
    view_state = _PARTIAL_VIEW_STATE.search(partial)
    return _entries(table.group(1)), view_state.group(1) if view_state else None


def apply_page(listing: MftListing, partial: str) -> MftListing:
    """Fold a PrimeFaces partial response in, and refuse a listing short of its own count."""
    entries, view_state = page_entries(partial, listing.link_url)
    resolved = replace(
        listing,
        entries=entries,
        view_state=view_state or listing.view_state,
        listing_sha256=hashlib.sha256(partial.encode("utf-8")).hexdigest(),
    )
    if len(entries) != listing.declared_count:
        raise ListingIncomplete(
            f"{listing.link_url} declares {listing.declared_count} rows and returned"
            f" {len(entries)}; the portal paginates at 250 and a short read loses artifacts"
        )
    return resolved


def listing_page_request(view_state: str, first: int = 0) -> dict[str, str]:
    """One partial request for a page of the folder; the rendered page itself caps at 250."""
    return {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "fileTable",
        "javax.faces.partial.execute": "fileTable",
        "javax.faces.partial.render": "fileTable",
        "fileTable": "fileTable",
        "fileTable_pagination": "true",
        "fileTable_first": str(first),
        "fileTable_rows": str(LISTING_PAGE_ROWS),
        "fileTable_skipChildren": "true",
        "fileTable_encodeFeature": "true",
        "fileList": "fileList",
        "fileList_SUBMIT": "1",
        "javax.faces.ViewState": view_state,
    }


def download_form(listing: MftListing, name: str) -> dict[str, str]:
    """The postback that yields one artifact. `fileList_SUBMIT` is what makes it a download."""
    entry = listing.entry(name)
    return {
        "fileList_SUBMIT": "1",
        "javax.faces.ViewState": listing.view_state,
        "fileTable_selection": "",
        "fileList": "fileList",
        entry.row_id: entry.row_id,
    }


def artifact_url(link_url: str, name: str) -> str:
    """glasswell's address for one entry. The portal ignores the query and renders the folder,
    so the URL resolves for a reader; the bytes come from the postback the transport makes."""
    return f"{link_url}?{FILENAME_PARAM}={quote(name, safe='')}"


def entry_name_from_url(url: httpx.URL) -> str:
    found = parse_qs(url.query.decode("utf-8")).get(FILENAME_PARAM)
    if not found:
        raise UnknownEntry(f"{url} names no {FILENAME_PARAM}")
    return found[0]


def fetch_listing(client: httpx.Client, link_url: str) -> MftListing:
    """The rendered page, then as many partial pages as its own row count says are missing."""
    page = client.get(link_url, timeout=LISTING_TIMEOUT_SECONDS)
    page.raise_for_status()
    listing = parse_listing(page.text, link_url=str(page.url))
    if len(listing.entries) == listing.declared_count:
        return listing

    collected: dict[str, MftEntry] = {}
    digest = hashlib.sha256()
    view_state = listing.view_state
    first = 0
    while len(collected) < listing.declared_count:
        partial = client.post(
            str(page.url),
            data=listing_page_request(view_state, first),
            headers={"faces-request": "partial/ajax", "x-requested-with": "XMLHttpRequest"},
            timeout=LISTING_TIMEOUT_SECONDS,
        )
        partial.raise_for_status()
        entries, refreshed = page_entries(partial.text, listing.link_url)
        digest.update(partial.text.encode("utf-8"))
        view_state = refreshed or view_state
        before = len(collected)
        collected.update({entry.name: entry for entry in entries})
        if len(collected) == before:
            break  # a page that adds nothing will not add anything on the next pass either
        first += LISTING_PAGE_ROWS

    resolved = replace(
        listing,
        entries=tuple(collected.values()),
        view_state=view_state,
        listing_sha256=digest.hexdigest(),
    )
    if len(resolved.entries) != listing.declared_count:
        raise ListingIncomplete(
            f"{listing.link_url} declares {listing.declared_count} rows and returned"
            f" {len(resolved.entries)}; the portal paginates at 250 and a short read loses"
            " artifacts"
        )
    return resolved


class MftTransport(httpx.BaseTransport):
    """Turns `GET <link>?filename=x` into the portal's postback for x, streaming the body."""

    def __init__(self, listing: MftListing, session: httpx.Client) -> None:
        self._listing = listing
        self._session = session

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        name = entry_name_from_url(request.url)
        body = urlencode(download_form(self._listing, name)).encode()
        upstream = self._session.build_request(
            "POST",
            self._listing.link_url,
            content=body,
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        )
        response = self._session.send(upstream, stream=True)
        disposition = response.headers.get("content-disposition", "")
        if response.status_code == 200 and name not in disposition:
            # A JSF postback that fails renders the folder again with status 200. Reading that
            # as the artifact is how a 294 KB HTML page becomes a county's well layer.
            response.close()
            raise ListingError(
                f"{name}: the portal answered with {disposition or 'no attachment'};"
                " the row id or the view state has expired"
            )
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=response.stream,
            extensions=response.extensions,
        )


class MftClient:
    """One resolved listing and the client `fetch_raw` downloads its artifacts through."""

    def __init__(self, link_url: str, *, session: httpx.Client | None = None) -> None:
        self._owns_session = session is None
        self._session = session or httpx.Client(
            follow_redirects=True,
            timeout=LISTING_TIMEOUT_SECONDS,
            headers={"user-agent": USER_AGENT},
        )
        self.listing = fetch_listing(self._session, link_url)
        self.client = httpx.Client(transport=MftTransport(self.listing, self._session))

    def url_for(self, name: str) -> str:
        self.listing.entry(name)
        return artifact_url(self.listing.link_url, name)

    def close(self) -> None:
        self.client.close()
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> MftClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
