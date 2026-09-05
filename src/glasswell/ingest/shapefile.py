"""A reader for zipped ESRI shapefiles. Source-specific meaning lives in the loaders."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

import shapefile
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

REQUIRED_MEMBERS = ("shp", "shx", "dbf")

_SEPARATORS = re.compile(r"[^a-z0-9]")


def _comparable(name: str) -> str:
    """A member stem or a layer suffix with case and separators removed.

    ECMC ships `Directional_Bottomhole_Locations.shp` for the layer registered as
    `directionalbottomholelocations`, and an endswith over the raw stem matched nothing: the
    regulator's punctuation is not a decision anybody here made, so neither side is compared on
    it. Measured on VM 111, 2026-09-04 20:06:30Z.
    """
    return _SEPARATORS.sub("", name.lower())


class UnknownProjection(ValueError):
    """The archive declares no projection, or one that resolves to no EPSG code."""


class MalformedArchive(ValueError):
    """The archive is missing a member the shapefile format requires."""


@dataclass(frozen=True, slots=True)
class ShapefileRecord:
    ordinal: int
    attributes: Mapping[str, Any]
    geometry: BaseGeometry | None

    @property
    def is_empty(self) -> bool:
        return self.geometry is None or self.geometry.is_empty


def epsg_from_prj(wkt: str) -> int:
    """Resolve the shipped .prj to an EPSG code, refusing to guess when it does not resolve."""
    from pyproj import CRS
    from pyproj.exceptions import CRSError

    try:
        code = CRS.from_wkt(wkt).to_epsg()
    except CRSError as error:
        raise UnknownProjection(f".prj does not parse as a CRS: {error}") from error
    if code is None:
        raise UnknownProjection(".prj resolves to no EPSG code; a datum is never assumed")
    return int(code)


class ZippedShapefile:
    """Reads .shp/.shx/.dbf/.prj out of a zip by extension, never by assumed filename.

    `layer_suffix` selects one of several shapefiles in one archive by the last characters of
    its stem — TX ships a county's surface points, bottom-hole points and well arcs as
    `well003s`, `well003b` and `well003l` inside a single `well003.zip`, and each carries its
    own `.prj` that the datum rule reads.

    `encoding` names the DBF code page. It defaults to pyshp's strict UTF-8 because a source
    that has always read is not re-decoded on a guess; a source whose language-driver byte
    declares otherwise passes it explicitly.
    """

    def __init__(
        self,
        archive: Path | str,
        *,
        layer_suffix: str | None = None,
        encoding: str | None = None,
    ) -> None:
        self.path = Path(archive)
        self.layer_suffix = layer_suffix
        self.encoding = encoding
        payloads: dict[str, bytes] = {}
        matched: set[str] = set()
        with zipfile.ZipFile(self.path) as bundle:
            for name in sorted(bundle.namelist()):
                if name.endswith("/"):
                    continue
                stem, _, extension = name.rpartition(".")
                extension = extension.lower()
                if layer_suffix is not None and not _comparable(stem).endswith(
                    _comparable(layer_suffix)
                ):
                    continue
                if extension in (*REQUIRED_MEMBERS, "prj"):
                    matched.add(stem)
                    if extension not in payloads:
                        payloads[extension] = bundle.read(name)
        # A suffix that names two layers names neither: a second candidate is a source that grew
        # a layer, not a tie for ZIP order to break. Only the Colorado callers have a conformance
        # row naming a member, so the message states the requirement instead of citing a rule.
        if layer_suffix is not None and len(matched) > 1:
            raise MalformedArchive(
                f"{self.path.name} has {len(matched)} members matching {layer_suffix!r}:"
                f" {', '.join(sorted(matched))}; a suffix must select exactly one"
            )
        missing = [member for member in REQUIRED_MEMBERS if member not in payloads]
        if missing:
            selector = f" matching {layer_suffix!r}" if layer_suffix else ""
            raise MalformedArchive(
                f"{self.path.name} has no .{', .'.join(missing)} member{selector}"
            )
        self._prj = payloads.get("prj")
        self._reader = shapefile.Reader(
            shp=io.BytesIO(payloads["shp"]),
            shx=io.BytesIO(payloads["shx"]),
            dbf=io.BytesIO(payloads["dbf"]),
            **({"encoding": encoding} if encoding is not None else {}),
        )
        self._epsg: int | None = None

    def __enter__(self) -> ZippedShapefile:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._reader.close()

    @property
    def source_epsg(self) -> int:
        if self._prj is None:
            raise UnknownProjection(
                f"{self.path.name} carries no .prj; the datum is never defaulted to 4326"
            )
        if self._epsg is None:
            self._epsg = epsg_from_prj(self._prj.decode("utf-8", errors="replace"))
        return self._epsg

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(field[0] for field in self._reader.fields[1:])

    def __len__(self) -> int:
        return len(self._reader)

    def __iter__(self) -> Iterator[ShapefileRecord]:
        for ordinal, entry in enumerate(self._reader.iterShapeRecords()):
            yield ShapefileRecord(
                ordinal=ordinal,
                attributes=dict(entry.record.as_dict()),
                geometry=_geometry(entry.shape),
            )


def _geometry(shape: shapefile.Shape) -> BaseGeometry | None:
    if shape.shapeType == shapefile.NULL or not getattr(shape, "points", ()):
        return None
    return shapely_shape(shape.__geo_interface__)
