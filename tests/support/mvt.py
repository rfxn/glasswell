"""A minimal MVT reader, so a tile assertion reads the wire rather than trusting the writer.

Mapbox Vector Tile 2.1: tile.layers is field 3, layer.keys field 3, layer.values field 4, and
a value message carries exactly one of string(1), float(2), double(3), int(4), uint(5),
sint(6), bool(7). That enum is the whole point here — `numeric` columns leave ST_AsMVT as
strings, and a string sorts lexicographically in a MapLibre expression.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

VALUE_TYPES = {
    1: "string",
    2: "float",
    3: "double",
    4: "int",
    5: "uint",
    6: "sint",
    7: "bool",
}


@dataclass(frozen=True, slots=True)
class Field:
    number: int
    wire_type: int
    payload: bytes | int


def _varint(data: bytes, index: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7


def fields(data: bytes) -> list[Field]:
    found: list[Field] = []
    index = 0
    while index < len(data):
        tag, index = _varint(data, index)
        number, wire_type = tag >> 3, tag & 0x07
        if wire_type == 0:
            value, index = _varint(data, index)
            found.append(Field(number, wire_type, value))
        elif wire_type == 2:
            length, index = _varint(data, index)
            found.append(Field(number, wire_type, data[index : index + length]))
            index += length
        elif wire_type == 5:
            found.append(Field(number, wire_type, data[index : index + 4]))
            index += 4
        elif wire_type == 1:
            found.append(Field(number, wire_type, data[index : index + 8]))
            index += 8
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
    return found


def layers(tile: bytes) -> list[bytes]:
    return [field.payload for field in fields(tile) if field.number == 3 and field.wire_type == 2]


def attribute_values(layer: bytes) -> list[tuple[str, object]]:
    """Every entry of the layer's value pool, as (declared type, decoded value)."""
    decoded: list[tuple[str, object]] = []
    for field in fields(layer):
        if field.number != 4 or field.wire_type != 2:
            continue
        entry = fields(field.payload)[0]
        kind = VALUE_TYPES[entry.number]
        if kind == "string":
            decoded.append((kind, bytes(entry.payload).decode("utf-8")))
        elif kind == "double":
            decoded.append((kind, struct.unpack("<d", entry.payload)[0]))
        elif kind == "float":
            decoded.append((kind, struct.unpack("<f", entry.payload)[0]))
        else:
            decoded.append((kind, entry.payload))
    return decoded


def layer_name(layer: bytes) -> str:
    """Layer.name is field 1 — how a two-layer tile says which bytes are the labels."""
    for field in fields(layer):
        if field.number == 1 and field.wire_type == 2:
            return bytes(field.payload).decode("utf-8")
    raise ValueError("layer carries no name")


def attribute_keys(layer: bytes) -> list[str]:
    return [
        bytes(field.payload).decode("utf-8")
        for field in fields(layer)
        if field.number == 3 and field.wire_type == 2
    ]


def feature_count(layer: bytes) -> int:
    """Layer.features is field 2; counting them is how a tile says how much it carries."""
    return sum(1 for field in fields(layer) if field.number == 2 and field.wire_type == 2)
