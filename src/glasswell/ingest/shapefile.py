"""A reader for zipped ESRI shapefiles. Source-specific meaning lives in the loaders."""

from __future__ import annotations

import io
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
    """Reads .shp/.shx/.dbf/.prj out of a zip by extension, never by assumed filename."""

    def __init__(self, archive: Path | str) -> None:
        self.path = Path(archive)
        payloads: dict[str, bytes] = {}
        with zipfile.ZipFile(self.path) as bundle:
            for name in bundle.namelist():
                if name.endswith("/"):
                    continue
                extension = name.rsplit(".", 1)[-1].lower()
                if extension in (*REQUIRED_MEMBERS, "prj") and extension not in payloads:
                    payloads[extension] = bundle.read(name)
        missing = [member for member in REQUIRED_MEMBERS if member not in payloads]
        if missing:
            raise MalformedArchive(f"{self.path.name} has no .{', .'.join(missing)} member")
        self._prj = payloads.get("prj")
        self._reader = shapefile.Reader(
            shp=io.BytesIO(payloads["shp"]),
            shx=io.BytesIO(payloads["shx"]),
            dbf=io.BytesIO(payloads["dbf"]),
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
