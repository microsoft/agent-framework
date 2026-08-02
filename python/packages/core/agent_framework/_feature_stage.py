# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import abc
import asyncio.coroutines
import contextlib
import functools
import inspect
import os
import sys
import typing
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

    DECLARATIVE_AGENTS = "DECLARATIVE_AGENTS"
    EVALS = "EVALS"
    FILE_HISTORY = "FILE_HISTORY"
    FIDES = "FIDES"
    FOUNDRY_TOOLS = "FOUNDRY_TOOLS"
    FOUNDRY_PREVIEW_TOOLS = "FOUNDRY_PREVIEW_TOOLS"
    FUNCTIONAL_WORKFLOWS = "FUNCTIONAL_WORKFLOWS"
    HARNESS = "HARNESS"
    MCP_LONG_RUNNING_TASKS = "MCP_LONG_RUNNING_TASKS"
    MCP_SKILLS = "MCP_SKILLS"
    PROGRESSIVE_TOOLS = "PROGRESSIVE_TOOLS"
    SESSION_STORE = "SESSION_STORE"
    TO_PROMPT_AGENT = "TO_PROMPT_AGENT"


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


# Sentinel attribute used to detect (and reuse) a formatter we've already
# installed. This lets the install be idempotent across re-imports / reloads
# and keeps a stable reference to the previous formatter for testing or
# external restoration via ``warnings.formatwarning = original``.
_FEATURE_STAGE_FORMATTER_MARKER = "__feature_stage_formatter__"


def _install_feature_stage_formatter() -> None:
    """Install a single-line formatter for FeatureStageWarning categories.

    The stdlib default formatter emits two lines (header + source snippet)
    which is noisy for our warnings — the offending class/function name is
    already in the message, so a one-line ``file:lineno: Category: message``
    is enough. Other warning categories are delegated to the previous
    formatter so we never change behaviour for unrelated warnings.

    The install is idempotent: if a formatter installed by this module is
    already in place, we leave it alone so re-imports (and any third-party
    formatter wrapped on top of ours) don't get wrapped multiple times.
    """
    current = warnings.formatwarning
    if getattr(current, _FEATURE_STAGE_FORMATTER_MARKER, False):
        return

    def _formatwarning(
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        line: str | None = None,
    ) -> str:
        if issubclass(category, FeatureStageWarning):
            return f"{filename}:{lineno}: {category.__name__}: {message}\n"
        return current(message, category, filename, lineno, line)

    setattr(_formatwarning, _FEATURE_STAGE_FORMATTER_MARKER, True)
    # Keep a reference to the wrapped formatter so callers (tests, embedders)
    # can restore the previous behaviour if they need to.
    _formatwarning.__wrapped__ = current  # type: ignore[attr-defined]
    warnings.formatwarning = _formatwarning


_install_feature_stage_formatter()


def _normalize_feature_id(feature_id: str | Enum) -> str:
    return str(feature_id.value if isinstance(feature_id, Enum) else feature_id)


def _get_object_name(obj: Any) -> str:
    return str(getattr(obj, "__qualname__", getattr(obj, "__name__", type(obj).__name__)))


def _get_descriptor_callable(obj: Any) -> Callable[..., Any]:
    return cast(Callable[..., Any], obj.__func__)


def _is_internal_framework_subclass(args: tuple[Any, ...]) -> bool:
    """Return whether an experimental subclass is defined inside an Agent Framework package."""
    subclass = next((arg for arg in args if isinstance(arg, type)), None)
    if subclass is None:
        return False
    module = subclass.__module__
    return module == "agent_framework" or module.startswith(("agent_framework.", "agent_framework_"))


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


_INTERNAL_FRAME_FILE = os.path.normcase(__file__)
# Module names whose frames we never want to surface as the caller. ``abc`` is
# the big one (its ``__new__`` shows up as ``<frozen abc>:106`` for ABC-driven
# subclass creation on modern CPython, so we cannot rely on filename matching).
# ``functools``/``typing``/``contextlib`` are added because they often wrap our
# decorators or appear in the metaclass call path.
_INTERNAL_FRAME_MODULES: frozenset[str] = frozenset({
    abc.__name__,
    functools.__name__,
    typing.__name__,
    contextlib.__name__,
})


def _is_internal_frame(frame: Any) -> bool:
    if os.path.normcase(frame.f_code.co_filename) == _INTERNAL_FRAME_FILE:
        return True
    module_name = frame.f_globals.get("__name__", "")
    if module_name in _INTERNAL_FRAME_MODULES:
        return True
    # Submodules of the skipped stdlib packages (``typing.ext``, ``functools``
    # wrappers under ``concurrent.futures._base``, etc.) are also wrappers we
    # don't want to surface.
    return any(module_name.startswith(prefix + ".") for prefix in _INTERNAL_FRAME_MODULES)


def _resolve_user_frame() -> tuple[str, int, str] | None:
    """Resolve the user frame that triggered an experimental warning.

    Walk the stack and return ``(filename, lineno, module_name)`` for the first
    frame outside this module and the wrapping/metaclass machinery.

    Returns ``None`` if no such frame is found; callers fall back to plain
    ``warnings.warn`` with a fixed stacklevel.
    """
    # Frame objects participate in reference cycles (``frame -> f_locals ->
    # frame``) and can delay GC if held implicitly. Capture the user frame's
    # data into plain values inside the try, and explicitly delete the frame
    # references in finally so we never leak frames across this call. This
    # follows CPython's own guidance for code that uses ``inspect.currentframe``.
    frame = inspect.currentframe()
    candidate: Any = None
    try:
        if frame is None:
            return None
        # Skip _resolve_user_frame itself + the warn helper that called it.
        candidate = frame.f_back.f_back if frame.f_back and frame.f_back.f_back else None
        while candidate is not None:
            if not _is_internal_frame(candidate):
                return (
                    candidate.f_code.co_filename,
                    candidate.f_lineno,
                    candidate.f_globals.get("__name__", "<unknown>"),
                )
            candidate = candidate.f_back
        return None
    finally:
        del frame, candidate


def _warn_on_feature_use(
    *,
    stage: FeatureStageName,
    feature_id: str | Enum,
    object_name: str,
    category: type[Warning],
) -> None:
    normalized_feature_id = _normalize_feature_id(feature_id)
    warning_key = (category, normalized_feature_id)
    if warning_key in _WARNED_FEATURES:
        return

    message = _build_stage_warning_message(stage=stage, feature_id=normalized_feature_id, object_name=object_name)
    user_frame = _resolve_user_frame()
    if user_frame is None:
        # Last-resort fallback: emit at the immediate caller of this helper.
        warnings.warn(message, category=category, stacklevel=2)
    else:
        filename, lineno, module = user_frame
        warnings.warn_explicit(
            message,
            category=category,
            filename=filename,
            lineno=lineno,
            module=module,
        )
    _WARNED_FEATURES.add(warning_key)


def warn_experimental_feature(
    message: str,
    *,
    feature_id: str | Enum,
    category: type[Warning] = ExperimentalWarning,
) -> bool:
    """Emit a one-time feature-stage warning for a feature not gated by a decorator.

    Some released APIs opt callers into experimental behaviour through individual
    parameters, which Python cannot decorate on their own. Call this to warn once per
    ``feature_id`` with a custom ``message`` (pointing at the caller's call site) and to
    seed the shared dedup registry, so a downstream decorated provider for the same
    ``feature_id`` does not warn a second time.

    Returns ``True`` when a warning was emitted, ``False`` when it was already emitted for
    this ``feature_id``/``category`` earlier in the process.
    """
    normalized_feature_id = _normalize_feature_id(feature_id)
    warning_key = (category, normalized_feature_id)
    if warning_key in _WARNED_FEATURES:
        return False

    user_frame = _resolve_user_frame()
    if user_frame is None:
        # Last-resort fallback: emit at the immediate caller of this helper.
        warnings.warn(message, category=category, stacklevel=2)
    else:
        filename, lineno, module = user_frame
        warnings.warn_explicit(
            message,
            category=category,
            filename=filename,
            lineno=lineno,
            module=module,
        )
    _WARNED_FEATURES.add(warning_key)
    return True


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
                )
            if original_new is not object.__new__:
                return original_new(cls, *args, **kwargs)
            if cls.__init__ is object.__init__ and (args or kwargs):
                raise TypeError(f"{cls.__name__}() takes no arguments")
            return original_new(cls)

        experimental_class.__new__ = staticmethod(__new__)

        original_init_subclass: Any = experimental_class.__init_subclass__
        if isinstance(original_init_subclass, MethodType):
            original_init_subclass_func = original_init_subclass.__func__

            @functools.wraps(original_init_subclass_func)
            def bound_init_subclass_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not _is_internal_framework_subclass(args):
                    _warn_on_feature_use(
                        stage=stage,
                        feature_id=feature_id,
                        object_name=object_name,
                        category=category,
                    )
                return original_init_subclass_func(*args, **kwargs)

            experimental_class.__init_subclass__ = classmethod(bound_init_subclass_wrapper)  # type: ignore[assignment]
        else:

            @functools.wraps(original_init_subclass)
            def init_subclass_wrapper(subclass: type[Any], /, *args: Any, **kwargs: Any) -> Any:
                if not _is_internal_framework_subclass((subclass, *args)):
                    _warn_on_feature_use(
                        stage=stage,
                        feature_id=feature_id,
                        object_name=object_name,
                        category=category,
                    )
                return original_init_subclass(*args, **kwargs)

            experimental_class.__init_subclass__ = classmethod(init_subclass_wrapper)  # type: ignore[assignment]

        return cast(FeatureStageT, experimental_class)

    @functools.wraps(obj)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _warn_on_feature_use(
            stage=stage,
            feature_id=feature_id,
            object_name=object_name,
            category=category,
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
