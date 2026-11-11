"""Convert Pydantic models to the JSON-schema subset accepted by structured outputs.

Constraints the API does not enforce (min/max, lengths) are stripped from the wire schema but are
still enforced locally because every response is re-validated with the Pydantic model.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel

_DROP_KEYS = {
    "title",
    "default",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
    "examples",
}


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"].split("/")[-1]
            return _resolve(copy.deepcopy(defs[ref]), defs)
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in _DROP_KEYS or k == "$defs":
                continue
            out[k] = _resolve(v, defs)
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"].keys())
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_resolve(v, defs) for v in node]
    return node


def to_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    result: dict[str, Any] = _resolve(raw, defs)
    return result
