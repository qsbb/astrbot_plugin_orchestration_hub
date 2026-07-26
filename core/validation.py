from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import SchemaValidationError


class SchemaRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, Mapping[str, Any]] = {}

    def register(self, reference: str, schema: Mapping[str, Any]) -> None:
        if not reference or not isinstance(schema, Mapping):
            raise ValueError("invalid schema registration")
        self._schemas[reference] = dict(schema)

    def resolve(self, schema: Mapping[str, Any] | str | None):
        if schema is None:
            return None
        if isinstance(schema, str):
            try:
                return self._schemas[schema]
            except KeyError as exc:
                raise SchemaValidationError("unknown JSON Schema reference", details={"schema": schema}) from exc
        return schema

    def validate(self, value: Any, schema: Mapping[str, Any] | str | None, *, direction: str) -> None:
        resolved = self.resolve(schema)
        if resolved is not None:
            _validate(value, resolved, "$", direction)


def _fail(path: str, direction: str, message: str) -> None:
    raise SchemaValidationError(f"{direction} schema validation failed: {message}", details={"path": path, "direction": direction})


def _validate(value: Any, schema: Mapping[str, Any], path: str, direction: str) -> None:
    if "$ref" in schema:
        _fail(path, direction, "external $ref is not supported; register the root schema by reference")
    if "const" in schema and value != schema["const"]:
        _fail(path, direction, "value does not equal const")
    if "enum" in schema and value not in schema["enum"]:
        _fail(path, direction, "value is not in enum")
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches_type(value, item) for item in expected):
            _fail(path, direction, f"expected one of {expected}")
    elif expected and not _matches_type(value, expected):
        _fail(path, direction, f"expected {expected}")

    if isinstance(value, Mapping):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                _fail(path, direction, f"missing required property {key}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in properties:
                _validate(item, properties[key], child, direction)
            elif additional is False:
                _fail(child, direction, "additional property is not allowed")
            elif isinstance(additional, Mapping):
                _validate(item, additional, child, direction)
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            _fail(path, direction, "too few properties")
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            _fail(path, direction, "too many properties")

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if "minItems" in schema and len(value) < schema["minItems"]:
            _fail(path, direction, "too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            _fail(path, direction, "too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate(item, item_schema, f"{path}[{index}]", direction)

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            _fail(path, direction, "string is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            _fail(path, direction, "string is too long")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            _fail(path, direction, "number must be finite")
        if "minimum" in schema and value < schema["minimum"]:
            _fail(path, direction, "number is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            _fail(path, direction, "number is above maximum")


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)
