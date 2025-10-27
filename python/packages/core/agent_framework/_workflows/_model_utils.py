# Copyright (c) Microsoft. All rights reserved.

import copy
import sys
from typing import Any, TypeVar, cast

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

TModel = TypeVar("TModel", bound="DictConvertible")


class DictConvertible:
    """Mixin providing conversion helpers for plain Python models."""

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls: type[TModel], data: dict[str, Any]) -> TModel:
        return cls(**data)  # type: ignore[arg-type]

    def clone(self, *, deep: bool = True) -> Self:
        return copy.deepcopy(self) if deep else copy.copy(self)  # type: ignore[return-value]

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls: type[TModel], raw: str) -> TModel:
        import json

        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("JSON payload must decode to a mapping")
        return cls.from_dict(cast(dict[str, Any], data))


def encode_value(value: Any) -> Any:
    """Recursively encode values for JSON-friendly serialization."""
    if isinstance(value, DictConvertible):
        return value.to_dict()
    if isinstance(value, dict):
        return {k: encode_value(v) for k, v in value.items()}  # type: ignore[misc]
    if isinstance(value, (list, tuple, set)):
        return [encode_value(v) for v in value]  # type: ignore[misc]
    return value
