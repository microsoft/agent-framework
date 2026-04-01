# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio.coroutines
import functools
import inspect
import sys
import warnings
from collections.abc import Callable
from enum import Enum
from types import MethodType
from typing import Any, Literal, TypeVar, cast

from ._docstrings import insert_docstring_block

FeatureStageT = TypeVar("FeatureStageT", bound=Callable[..., Any])

FeatureStageName = Literal["experimental", "release_candidate"]

# Optional feature-stage metadata for warnings and best-effort introspection.
_FEATURE_ID_ATTR = "__feature_id__"
_FEATURE_STAGE_ATTR = "__feature_stage__"
_WARNED_FEATURES: set[tuple[type[Warning], str]] = set()
_EXPERIMENTAL_DOCSTRING = """\
.. warning:: Experimental

    This API is experimental and subject to change or removal
    in future versions without notice.
"""
_RELEASE_CANDIDATE_DOCSTRING = """\
.. note:: Release candidate

    This API is in release-candidate stage and may receive
    minor refinements before it is considered generally available.
"""


class ExperimentalFeature(str, Enum):
    """Current experimental feature IDs.

    This enum is a stage-scoped inventory, not a stable introspection surface.
    Members may move or be removed as features advance. The `__feature_id__`
    attribute is also optional stage metadata and may disappear when a feature
    is released, so consumer code should use `getattr(...)` rather than relying
    on enum membership or attribute presence over time.
    """

    SKILLS = "SKILLS"


class ReleaseCandidateFeature(str, Enum):
    """Current release-candidate feature IDs.

    This enum is a stage-scoped inventory, not a stable introspection surface.
    Members may move or be removed as features advance. The `__feature_id__`
    attribute is also optional stage metadata and may disappear when a feature
    is released, so consumer code should use `getattr(...)` rather than relying
    on enum membership or attribute presence over time.
    """


class FeatureStageWarning(FutureWarning):
    """Base warning category for staged APIs."""


class ExperimentalWarning(FeatureStageWarning):
    """Warning emitted when an experimental API is used."""


def _normalize_feature_id(feature_id: str | Enum) -> str:
    return str(feature_id.value if isinstance(feature_id, Enum) else feature_id)


def _get_object_name(obj: Any) -> str:
    return str(getattr(obj, "__qualname__", getattr(obj, "__name__", type(obj).__name__)))


def _get_descriptor_callable(obj: Any) -> Callable[..., Any]:
    return cast(Callable[..., Any], obj.__func__)


def _is_protocol_class(obj: Any) -> bool:
    return isinstance(obj, type) and bool(getattr(obj, "_is_protocol", False))


def _build_stage_warning_message(*, stage: FeatureStageName, feature_id: str, object_name: str) -> str:
    if stage == "experimental":
        return (
            f"[{feature_id}] {object_name} is experimental and may change or be removed in future versions "
            "without notice."
        )

    return (
        f"[{feature_id}] {object_name} is in release-candidate stage and may receive minor refinements before it is "
        "considered generally available."
    )


def _set_feature_stage_metadata(obj: Any, *, stage: FeatureStageName, feature_id: str) -> None:
    setattr(obj, _FEATURE_STAGE_ATTR, stage)
    setattr(obj, _FEATURE_ID_ATTR, feature_id)


def _warn_on_feature_use(
    *,
    stage: FeatureStageName,
    feature_id: str,
    object_name: str,
    category: type[Warning],
    stacklevel: int,
) -> None:
    warning_key = (category, feature_id)
    if warning_key in _WARNED_FEATURES:
        return

    warnings.warn(
        _build_stage_warning_message(stage=stage, feature_id=feature_id, object_name=object_name),
        category=category,
        stacklevel=stacklevel,
    )
    _WARNED_FEATURES.add(warning_key)


def _add_runtime_warning(
    obj: FeatureStageT,
    *,
    stage: FeatureStageName,
    feature_id: str,
    category: type[Warning],
) -> FeatureStageT:
    object_name = _get_object_name(obj)

    if isinstance(obj, type):
        experimental_class = cast(type[Any], obj)
        original_new: Any = experimental_class.__new__

        @functools.wraps(original_new)
        def __new__(cls: type[Any], /, *args: Any, **kwargs: Any) -> Any:
            if cls is experimental_class:
                _warn_on_feature_use(
                    stage=stage,
                    feature_id=feature_id,
                    object_name=object_name,
                    category=category,
                    stacklevel=3,
                )
            if original_new is not object.__new__:
                return original_new(cls, *args, **kwargs)
            if cls.__init__ is object.__init__ and (args or kwargs):
                raise TypeError(f"{cls.__name__}() takes no arguments")
            return original_new(cls)

        experimental_class.__new__ = staticmethod(__new__)  # type: ignore[assignment]

        original_init_subclass: Any = experimental_class.__init_subclass__
        if isinstance(original_init_subclass, MethodType):
            original_init_subclass_func = original_init_subclass.__func__

            @functools.wraps(original_init_subclass_func)
            def bound_init_subclass_wrapper(*args: Any, **kwargs: Any) -> Any:
                _warn_on_feature_use(
                    stage=stage,
                    feature_id=feature_id,
                    object_name=object_name,
                    category=category,
                    stacklevel=3,
                )
                return original_init_subclass_func(*args, **kwargs)

            experimental_class.__init_subclass__ = classmethod(bound_init_subclass_wrapper)  # type: ignore[assignment]
        else:

            @functools.wraps(original_init_subclass)
            def init_subclass_wrapper(*args: Any, **kwargs: Any) -> Any:
                _warn_on_feature_use(
                    stage=stage,
                    feature_id=feature_id,
                    object_name=object_name,
                    category=category,
                    stacklevel=3,
                )
                return original_init_subclass(*args, **kwargs)

            experimental_class.__init_subclass__ = init_subclass_wrapper  # type: ignore[assignment]

        return cast(FeatureStageT, experimental_class)

    @functools.wraps(obj)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _warn_on_feature_use(
            stage=stage,
            feature_id=feature_id,
            object_name=object_name,
            category=category,
            stacklevel=3,
        )
        return obj(*args, **kwargs)

    if inspect.iscoroutinefunction(obj):
        if sys.version_info >= (3, 12):
            wrapper = inspect.markcoroutinefunction(wrapper)
        else:
            wrapper._is_coroutine = asyncio.coroutines._is_coroutine  # type: ignore[attr-defined]

    return cast(FeatureStageT, wrapper)


def _feature_stage(
    *,
    stage: FeatureStageName,
    feature_id: str | Enum,
    docstring_block: str,
    warning_category: type[Warning] | None,
) -> Callable[[FeatureStageT], FeatureStageT]:
    normalized_feature_id = _normalize_feature_id(feature_id)

    def decorator(obj: FeatureStageT) -> FeatureStageT:
        descriptor_wrapper: Callable[[Any], Any] | None = None
        target: Any = obj

        if isinstance(obj, staticmethod):
            descriptor_wrapper = staticmethod
            target = _get_descriptor_callable(obj)
        elif isinstance(obj, classmethod):
            descriptor_wrapper = classmethod
            target = _get_descriptor_callable(obj)

        if not callable(target):
            raise TypeError(f"{stage} decorator can only be applied to classes and callables, not {obj!r}.")

        is_protocol_class = _is_protocol_class(target)
        decorated: Any = target
        if warning_category is not None and not is_protocol_class:
            decorated = _add_runtime_warning(
                target,
                stage=stage,
                feature_id=normalized_feature_id,
                category=warning_category,
            )

        updated_docstring = insert_docstring_block(decorated.__doc__, block=docstring_block)
        if updated_docstring is not None:
            decorated.__doc__ = updated_docstring

        # runtime_checkable Protocol classes treat added class attributes as protocol members
        # on older Python versions, which breaks isinstance/issubclass checks.
        if not is_protocol_class:
            _set_feature_stage_metadata(decorated, stage=stage, feature_id=normalized_feature_id)
        if descriptor_wrapper is not None:
            return cast(FeatureStageT, descriptor_wrapper(decorated))

        return cast(FeatureStageT, decorated)

    return decorator


def experimental(*, feature_id: ExperimentalFeature) -> Callable[[FeatureStageT], FeatureStageT]:
    """Mark a class or callable as experimental."""
    return _feature_stage(
        stage="experimental",
        feature_id=feature_id,
        docstring_block=_EXPERIMENTAL_DOCSTRING,
        warning_category=ExperimentalWarning,
    )


def release_candidate(
    *,
    feature_id: ReleaseCandidateFeature,
) -> Callable[[FeatureStageT], FeatureStageT]:
    """Mark a class or callable as release-candidate."""
    return _feature_stage(
        stage="release_candidate",
        feature_id=feature_id,
        docstring_block=_RELEASE_CANDIDATE_DOCSTRING,
        warning_category=None,
    )
