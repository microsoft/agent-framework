# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ._const import INTERNAL_SOURCE_ID
from ._executor import Executor
from ._model_utils import DictConvertible, encode_value

logger = logging.getLogger(__name__)


def _extract_function_name(func: Callable[..., Any]) -> str:
    """Map a Python callable to a concise, human-focused identifier.

    The workflow graph persists references to callables by recording only an
    identifier. This helper inspects standard callable metadata and picks a
    stable value so that serialized representations remain intelligible when
    they are later rendered in logs or reconstructed during deserialization.

    Examples:
        .. code-block:: python

            def threshold(value: float) -> bool:
                return value > 0.5


            assert _extract_function_name(threshold) == "threshold"
    """
    if hasattr(func, "__name__"):
        name = func.__name__
        return name if name != "<lambda>" else "<lambda>"
    return "<callable>"


def _missing_callable(name: str) -> Callable[..., Any]:
    """Create a defensive placeholder for callables that cannot be restored.

    When a workflow is deserialized in an environment that lacks the original
    Python callable, we install a proxy that fails loudly. Surfacing the error
    at invocation time preserves a clean separation between I/O concerns and
    runtime execution, while making it obvious which callable needs to be
    re-registered.

    Examples:
        .. code-block:: python

            guard = _missing_callable("transform_price")
            try:
                guard()
            except RuntimeError as exc:
                assert "transform_price" in str(exc)
    """

    def _raise(*_: Any, **__: Any) -> Any:
        raise RuntimeError(f"Callable '{name}' is unavailable after serialization")

    return _raise


@dataclass(init=False)
class Edge(DictConvertible):
    """Model a directed, optionally-conditional hand-off between two executors.

    Each `Edge` captures the minimal metadata required to move a message from
    one executor to another inside the workflow graph. It optionally embeds a
    boolean predicate that decides if the edge should be taken at runtime. By
    serialising the edge down to primitives we can reconstruct the topology of
    a workflow irrespective of the original Python process.

    Examples:
        .. code-block:: python

            edge = Edge(source_id="ingest", target_id="score", condition=lambda payload: payload["ready"])
            assert edge.should_route({"ready": True}) is True
            assert edge.should_route({"ready": False}) is False
    """

    ID_SEPARATOR: ClassVar[str] = "->"

    source_id: str
    target_id: str
    condition_name: str | None
    _condition: Callable[[Any], bool] | None = field(default=None, repr=False, compare=False)

    def __init__(
        self,
        source_id: str,
        target_id: str,
        condition: Callable[[Any], bool] | None = None,
        *,
        condition_name: str | None = None,
    ) -> None:
        """Initialize a fully-specified edge between two workflow executors.

        Parameters
        ----------
        source_id:
            Canonical identifier of the upstream executor instance.
        target_id:
            Canonical identifier of the downstream executor instance.
        condition:
            Optional predicate that receives the message payload and returns
            `True` when the edge should be traversed. When omitted, the edge is
            considered unconditionally active.
        condition_name:
            Optional override that pins a human-friendly name for the condition
            when the callable cannot be introspected (for example after
            deserialization).

        Examples:
            .. code-block:: python

                edge = Edge("fetch", "parse", condition=lambda data: data.is_valid)
                assert edge.source_id == "fetch"
                assert edge.target_id == "parse"
        """
        if not source_id:
            raise ValueError("Edge source_id must be a non-empty string")
        if not target_id:
            raise ValueError("Edge target_id must be a non-empty string")
        self.source_id = source_id
        self.target_id = target_id
        self._condition = condition
        self.condition_name = _extract_function_name(condition) if condition is not None else condition_name

    @property
    def id(self) -> str:
        """Return the stable identifier used to reference this edge.

        The identifier combines the source and target executor identifiers with
        a deterministic separator. This allows other graph structures such as
        adjacency lists or visualisations to refer to an edge without carrying
        the full object.

        Examples:
            .. code-block:: python

                edge = Edge("reader", "writer")
                assert edge.id == "reader->writer"
        """
        return f"{self.source_id}{self.ID_SEPARATOR}{self.target_id}"

    def should_route(self, data: Any) -> bool:
        """Evaluate the edge predicate against an incoming payload.

        When the edge was defined without an explicit predicate the method
        returns `True`, signalling an unconditional routing rule. Otherwise the
        user-supplied callable decides whether the message should proceed along
        this edge. Any exception raised by the callable is deliberately allowed
        to surface to the caller to avoid masking logic bugs.

        Examples:
            .. code-block:: python

                edge = Edge("stage1", "stage2", condition=lambda payload: payload["score"] > 0.8)
                assert edge.should_route({"score": 0.9}) is True
                assert edge.should_route({"score": 0.4}) is False
        """
        if self._condition is None:
            return True
        return self._condition(data)

    def to_dict(self) -> dict[str, Any]:
        """Produce a JSON-serialisable view of the edge metadata.

        The representation includes the source and target executor identifiers
        plus the condition name when it is known. Serialisation intentionally
        omits the live callable to keep payloads transport-friendly.

        Examples:
            .. code-block:: python

                edge = Edge("reader", "writer", condition=lambda payload: payload["ok"])
                snapshot = edge.to_dict()
                assert snapshot == {"source_id": "reader", "target_id": "writer", "condition_name": "<lambda>"}
        """
        payload = {"source_id": self.source_id, "target_id": self.target_id}
        if self.condition_name is not None:
            payload["condition_name"] = self.condition_name
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Edge":
        """Reconstruct an `Edge` from its serialised dictionary form.

        The deserialised edge will lack the executable predicate because we do
        not attempt to hydrate Python callables from storage. Instead, the
        stored `condition_name` is preserved so that downstream consumers can
        detect missing callables and re-register them where appropriate.

        Examples:
            .. code-block:: python

                payload = {"source_id": "reader", "target_id": "writer", "condition_name": "is_ready"}
                edge = Edge.from_dict(payload)
                assert edge.source_id == "reader"
                assert edge.condition_name == "is_ready"
        """
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            condition=None,
            condition_name=data.get("condition_name"),
        )


@dataclass
class Case:
    """Runtime wrapper combining a switch-case predicate with its target.

    Each `Case` couples a boolean predicate with the executor that should
    handle the message when the predicate evaluates to `True`. The runtime
    keeps this lightweight container separate from the serialisable
    `SwitchCaseEdgeGroupCase` so that execution can operate with live callables
    without polluting persisted state.

    Examples:
        .. code-block:: python

            class JsonExecutor(Executor):
                def __init__(self) -> None:
                    super().__init__(id="json", defer_discovery=True)


            processor = JsonExecutor()
            case = Case(condition=lambda payload: payload["kind"] == "json", target=processor)
            assert case.target.id == "json"
    """

    condition: Callable[[Any], bool]
    target: Executor


@dataclass
class Default:
    """Runtime representation of the default branch in a switch-case group.

    The default branch is invoked only when no other case predicates match. In
    practice it is guaranteed to exist so that routing never produces an empty
    target.

    Examples:
        .. code-block:: python

            class DeadLetterExecutor(Executor):
                def __init__(self) -> None:
                    super().__init__(id="dead_letter", defer_discovery=True)


            fallback = Default(target=DeadLetterExecutor())
            assert fallback.target.id == "dead_letter"
    """

    target: Executor


@dataclass(init=False)
class EdgeGroup(DictConvertible):
    """Bundle edges that share a common routing semantics under a single id.

    The workflow runtime manipulates `EdgeGroup` instances rather than raw
    edges so it can reason about higher-order routing behaviours such as
    fan-out, fan-in, switch-case, and other graph patterns. The base class stores the
    identifying information and handles serialisation duties so specialised
    groups need only maintain their additional state.

    Examples:
        .. code-block:: python

            group = EdgeGroup([Edge("source", "sink")])
            assert group.source_executor_ids == ["source"]
    """

    id: str
    type: str
    edges: list[Edge]

    from builtins import type as builtin_type

    _TYPE_REGISTRY: ClassVar[dict[str, builtin_type["EdgeGroup"]]] = {}

    def __init__(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        id: str | None = None,
        type: str | None = None,
    ) -> None:
        """Construct an edge group shell around a set of `Edge` instances.

        Parameters
        ----------
        edges:
            Sequence of edges that participate in this group. When omitted we
            start from an empty list so subclasses can append later.
        id:
            Stable identifier for the group. Defaults to a random UUID so
            serialised graphs remain uniquely addressable.
        type:
            Logical discriminator used to recover the appropriate subclass when
            de-serialising.

        Examples:
            .. code-block:: python

                edges = [Edge("validate", "persist")]
                group = EdgeGroup(edges, id="stage", type="Custom")
                assert group.to_dict()["type"] == "Custom"
        """
        self.id = id or f"{self.__class__.__name__}/{uuid.uuid4()}"
        self.type = type or self.__class__.__name__
        self.edges = list(edges) if edges is not None else []

    @property
    def source_executor_ids(self) -> list[str]:
        """Return the deduplicated list of upstream executor ids.

        The property preserves order-of-first-appearance so the caller can rely
        on deterministic iteration when reconstructing graph topology.

        Examples:
            .. code-block:: python

                group = EdgeGroup([Edge("read", "write"), Edge("read", "archive")])
                assert group.source_executor_ids == ["read"]
        """
        return list(dict.fromkeys(edge.source_id for edge in self.edges))

    @property
    def target_executor_ids(self) -> list[str]:
        """Return the ordered, deduplicated list of downstream executor ids.

        Examples:
            .. code-block:: python

                group = EdgeGroup([Edge("read", "write"), Edge("read", "archive")])
                assert group.target_executor_ids == ["write", "archive"]
        """
        return list(dict.fromkeys(edge.target_id for edge in self.edges))

    def to_dict(self) -> dict[str, Any]:
        """Serialise the group metadata and contained edges into primitives.

        The payload captures each edge through its own `to_dict` call, enabling
        round-tripping through formats such as JSON without leaking Python
        objects.

        Examples:
            .. code-block:: python

                group = EdgeGroup([Edge("read", "write")])
                snapshot = group.to_dict()
                assert snapshot["edges"][0]["source_id"] == "read"
        """
        return {
            "id": self.id,
            "type": self.type,
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def register(cls, subclass: builtin_type["EdgeGroup"]) -> builtin_type["EdgeGroup"]:
        """Register a subclass so deserialisation can recover the right type.

        Registration is typically performed via the decorator syntax applied to
        each concrete edge group. The registry stores classes by their
        `__name__`, which must therefore remain stable across versions when
        persisted workflows are in circulation.

        Examples:
            .. code-block:: python

                @EdgeGroup.register
                class CustomGroup(EdgeGroup):
                    pass


                assert EdgeGroup._TYPE_REGISTRY["CustomGroup"] is CustomGroup
        """
        cls._TYPE_REGISTRY[subclass.__name__] = subclass
        return subclass

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EdgeGroup":
        """Hydrate the correct `EdgeGroup` subclass from serialised state.

        The method inspects the `type` field, allocates the corresponding class
        without executing subclass `__init__`, and then manually restores any
        subtype-specific attributes. This keeps deserialisation deterministic
        even for complex group types that configure additional runtime
        callables.

        Examples:
            .. code-block:: python

                payload = {"type": "EdgeGroup", "edges": [{"source_id": "a", "target_id": "b"}]}
                group = EdgeGroup.from_dict(payload)
                assert isinstance(group, EdgeGroup)
        """
        group_type = data.get("type", "EdgeGroup")
        target_cls = cls._TYPE_REGISTRY.get(group_type, EdgeGroup)
        edges = [Edge.from_dict(entry) for entry in data.get("edges", [])]

        obj = target_cls.__new__(target_cls)  # type: ignore[misc]
        EdgeGroup.__init__(obj, edges=edges, id=data.get("id"), type=group_type)

        # Handle FanOutEdgeGroup-specific attributes
        if isinstance(obj, FanOutEdgeGroup):
            obj.selection_func_name = data.get("selection_func_name")  # type: ignore[attr-defined]
            obj._selection_func = (  # type: ignore[attr-defined]
                None
                if obj.selection_func_name is None  # type: ignore[attr-defined]
                else _missing_callable(obj.selection_func_name)  # type: ignore[attr-defined]
            )
            obj._target_ids = [edge.target_id for edge in obj.edges]  # type: ignore[attr-defined]

        # Handle SwitchCaseEdgeGroup-specific attributes
        if isinstance(obj, SwitchCaseEdgeGroup):
            cases_payload = data.get("cases", [])
            restored_cases: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault] = []
            for case_data in cases_payload:
                case_type = case_data.get("type")
                if case_type == "Default":
                    restored_cases.append(SwitchCaseEdgeGroupDefault.from_dict(case_data))
                else:
                    restored_cases.append(SwitchCaseEdgeGroupCase.from_dict(case_data))
            obj.cases = restored_cases  # type: ignore[attr-defined]
            obj._selection_func = _missing_callable("switch_case_selection")  # type: ignore[attr-defined]

        return obj


@EdgeGroup.register
@dataclass(init=False)
class SingleEdgeGroup(EdgeGroup):
    """Convenience wrapper for a solitary edge, keeping the group API uniform."""

    def __init__(
        self,
        source_id: str,
        target_id: str,
        condition: Callable[[Any], bool] | None = None,
        *,
        id: str | None = None,
    ) -> None:
        """Create a one-to-one edge group between two executors.

        Examples:
            .. code-block:: python

                group = SingleEdgeGroup("ingest", "validate")
                assert group.edges[0].source_id == "ingest"
        """
        edge = Edge(source_id=source_id, target_id=target_id, condition=condition)
        super().__init__([edge], id=id, type=self.__class__.__name__)


@EdgeGroup.register
@dataclass(init=False)
class FanOutEdgeGroup(EdgeGroup):
    """Represent a broadcast-style edge group with optional selection logic.

    A fan-out forwards a message produced by a single source executor to one
    or more downstream executors. At runtime we may further narrow the targets
    by executing a `selection_func` that inspects the payload and returns the
    subset of ids that should receive the message.
    """

    selection_func_name: str | None
    _selection_func: Callable[[Any, list[str]], list[str]] | None
    _target_ids: list[str]

    def __init__(
        self,
        source_id: str,
        target_ids: Sequence[str],
        selection_func: Callable[[Any, list[str]], list[str]] | None = None,
        *,
        selection_func_name: str | None = None,
        id: str | None = None,
    ) -> None:
        """Create a fan-out mapping from a single source to many targets.

        Parameters
        ----------
        source_id:
            Identifier of the upstream executor broadcasting the message.
        target_ids:
            Ordered set of downstream executor identifiers that may receive the
            message. At least two targets are required to preserve the fan-out
            semantics.
        selection_func:
            Optional callable that returns the subset of `target_ids` that
            should be active for a given payload. The callable receives the
            original message plus a copy of all configured target ids.
        selection_func_name:
            Static identifier used when persisting the fan-out. Needed when the
            callable cannot be introspected or is unavailable during
            deserialisation.
        id:
            Stable identifier for the group; defaults to an autogenerated UUID.

        Examples:
            .. code-block:: python

                def choose_targets(message: dict[str, Any], available: list[str]) -> list[str]:
                    return [target for target in available if message.get(target)]


                group = FanOutEdgeGroup("sensor", ["db", "cache"], selection_func=choose_targets)
                assert group.selection_func is choose_targets
        """
        if len(target_ids) <= 1:
            raise ValueError("FanOutEdgeGroup must contain at least two targets.")

        edges = [Edge(source_id=source_id, target_id=target) for target in target_ids]
        super().__init__(edges, id=id, type=self.__class__.__name__)

        self._target_ids = list(target_ids)
        self._selection_func = selection_func
        self.selection_func_name = (
            _extract_function_name(selection_func) if selection_func is not None else selection_func_name
        )

    @property
    def target_ids(self) -> list[str]:
        """Return a shallow copy of the configured downstream executor ids.

        The list is defensively copied to prevent callers from mutating the
        internal state while still providing deterministic ordering.

        Examples:
            .. code-block:: python

                group = FanOutEdgeGroup("node", ["alpha", "beta"])
                assert group.target_ids == ["alpha", "beta"]
        """
        return list(self._target_ids)

    @property
    def selection_func(self) -> Callable[[Any, list[str]], list[str]] | None:
        """Expose the runtime callable used to select active fan-out targets.

        When no selection function was supplied the property returns `None`,
        signalling that all targets must receive the payload.

        Examples:
            .. code-block:: python

                group = FanOutEdgeGroup("source", ["x", "y"], selection_func=None)
                assert group.selection_func is None
        """
        return self._selection_func

    def to_dict(self) -> dict[str, Any]:
        """Serialise the fan-out group while preserving selection metadata.

        In addition to the base `EdgeGroup` payload we embed the human-friendly
        name of the selection function. The callable itself is not persisted.

        Examples:
            .. code-block:: python

                group = FanOutEdgeGroup("source", ["a", "b"], selection_func=lambda *_: ["a"])
                snapshot = group.to_dict()
                assert snapshot["selection_func_name"] == "<lambda>"
        """
        payload = super().to_dict()
        payload["selection_func_name"] = self.selection_func_name
        return payload


@EdgeGroup.register
@dataclass(init=False)
class FanInEdgeGroup(EdgeGroup):
    """Represent a converging set of edges that feed a single downstream executor.

    Fan-in groups are typically used when multiple upstream stages independently
    produce messages that should all arrive at the same downstream processor.
    """

    def __init__(self, source_ids: Sequence[str], target_id: str, *, id: str | None = None) -> None:
        """Build a fan-in mapping that merges several sources into one target.

        Parameters
        ----------
        source_ids:
            Sequence of upstream executor identifiers contributing messages.
        target_id:
            Downstream executor that receives every message emitted by the
            sources.
        id:
            Optional explicit identifier for the edge group.

        Examples:
            .. code-block:: python

                group = FanInEdgeGroup(["parser", "enricher"], target_id="writer")
                assert group.to_dict()["edges"][0]["target_id"] == "writer"
        """
        if len(source_ids) <= 1:
            raise ValueError("FanInEdgeGroup must contain at least two sources.")

        edges = [Edge(source_id=source, target_id=target_id) for source in source_ids]
        super().__init__(edges, id=id, type=self.__class__.__name__)


@dataclass(init=False)
class SwitchCaseEdgeGroupCase(DictConvertible):
    """Persistable description of a single conditional branch in a switch-case.

    Unlike the runtime `Case` object this serialisable variant stores only the
    target identifier and a descriptive name for the predicate. When the
    underlying callable is unavailable during deserialisation we substitute a
    proxy placeholder that fails loudly, ensuring the missing dependency is
    immediately visible.
    """

    target_id: str
    condition_name: str | None
    type: str
    _condition: Callable[[Any], bool] = field(repr=False, compare=False)

    def __init__(
        self,
        condition: Callable[[Any], bool] | None,
        target_id: str,
        *,
        condition_name: str | None = None,
    ) -> None:
        """Record the routing metadata for a conditional case branch.

        Parameters
        ----------
        condition:
            Optional live predicate. When omitted we fall back to a placeholder
            that raises at runtime to highlight missing registrations.
        target_id:
            Identifier of the executor that should handle messages when the
            predicate succeeds.
        condition_name:
            Human-friendly label for the predicate used for diagnostics and
            on-disk persistence.

        Examples:
            .. code-block:: python

                case = SwitchCaseEdgeGroupCase(lambda payload: payload["type"] == "csv", target_id="csv_handler")
                assert case.condition_name == "<lambda>"
        """
        if not target_id:
            raise ValueError("SwitchCaseEdgeGroupCase requires a target_id")
        self.target_id = target_id
        self.type = "Case"
        if condition is not None:
            self._condition = condition
            self.condition_name = _extract_function_name(condition)
        else:
            safe_name = condition_name or "<missing_condition>"
            self._condition = _missing_callable(safe_name)
            self.condition_name = condition_name

    @property
    def condition(self) -> Callable[[Any], bool]:
        """Return the predicate associated with this case.

        The placeholder installed during deserialisation raises a
        `RuntimeError` when invoked so that workflow authors are forced to
        provide the missing callable explicitly.

        Examples:
            .. code-block:: python

                case = SwitchCaseEdgeGroupCase(None, target_id="missing", condition_name="needs_registration")
                guard = case.condition
                try:
                    guard({})
                except RuntimeError:
                    pass
        """
        return self._condition

    def to_dict(self) -> dict[str, Any]:
        """Serialise the case metadata without the executable predicate.

        Examples:
            .. code-block:: python

                case = SwitchCaseEdgeGroupCase(lambda _: True, target_id="handler")
                assert case.to_dict()["target_id"] == "handler"
        """
        payload = {"target_id": self.target_id, "type": self.type}
        if self.condition_name is not None:
            payload["condition_name"] = self.condition_name
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SwitchCaseEdgeGroupCase":
        """Instantiate a case from its serialised dictionary payload.

        Examples:
            .. code-block:: python

                payload = {"target_id": "handler", "condition_name": "is_ready"}
                case = SwitchCaseEdgeGroupCase.from_dict(payload)
                assert case.target_id == "handler"
        """
        return cls(
            condition=None,
            target_id=data["target_id"],
            condition_name=data.get("condition_name"),
        )


@dataclass(init=False)
class SwitchCaseEdgeGroupDefault(DictConvertible):
    """Persistable descriptor for the fallback branch of a switch-case group.

    The default branch is guaranteed to exist and is invoked when every other
    case predicate fails to match the payload.
    """

    target_id: str
    type: str

    def __init__(self, target_id: str) -> None:
        """Point the default branch toward the given executor identifier.

        Examples:
            .. code-block:: python

                fallback = SwitchCaseEdgeGroupDefault(target_id="dead_letter")
                assert fallback.target_id == "dead_letter"
        """
        if not target_id:
            raise ValueError("SwitchCaseEdgeGroupDefault requires a target_id")
        self.target_id = target_id
        self.type = "Default"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the default branch metadata for persistence or logging.

        Examples:
            .. code-block:: python

                fallback = SwitchCaseEdgeGroupDefault("dead_letter")
                assert fallback.to_dict()["type"] == "Default"
        """
        return {"target_id": self.target_id, "type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SwitchCaseEdgeGroupDefault":
        """Recreate the default branch from its persisted form.

        Examples:
            .. code-block:: python

                payload = {"target_id": "dead_letter", "type": "Default"}
                fallback = SwitchCaseEdgeGroupDefault.from_dict(payload)
                assert fallback.target_id == "dead_letter"
        """
        return cls(target_id=data["target_id"])


@EdgeGroup.register
@dataclass(init=False)
class SwitchCaseEdgeGroup(FanOutEdgeGroup):
    """Fan-out variant that mimics a traditional switch/case control flow.

    Each case inspects the message payload and decides whether it should handle
    the message. Exactly one case-or the default branch-returns a target at
    runtime, preserving single-dispatch semantics.
    """

    cases: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault]

    def __init__(
        self,
        source_id: str,
        cases: Sequence[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault],
        *,
        id: str | None = None,
    ) -> None:
        """Configure a switch/case routing structure for a single source executor.

        Parameters
        ----------
        source_id:
            Identifier of the executor producing the message to be routed.
        cases:
            Ordered sequence of case descriptors concluding with a
            `SwitchCaseEdgeGroupDefault`. Ordering matters because the runtime
            evaluates each branch sequentially until one matches.
        id:
            Optional explicit identifier for the edge group.

        Examples:
            .. code-block:: python

                cases = [
                    SwitchCaseEdgeGroupCase(lambda payload: payload["kind"] == "csv", target_id="process_csv"),
                    SwitchCaseEdgeGroupDefault(target_id="process_default"),
                ]
                group = SwitchCaseEdgeGroup("router", cases)
                encoded = group.to_dict()
                assert encoded["cases"][0]["type"] == "Case"
        """
        if len(cases) < 2:
            raise ValueError("SwitchCaseEdgeGroup must contain at least two cases (including the default case).")

        default_cases = [case for case in cases if isinstance(case, SwitchCaseEdgeGroupDefault)]
        if len(default_cases) != 1:
            raise ValueError("SwitchCaseEdgeGroup must contain exactly one default case.")

        if not isinstance(cases[-1], SwitchCaseEdgeGroupDefault):
            logger.warning(
                "Default case in the switch-case edge group is not the last case. "
                "This may result in unexpected behavior."
            )

        def selection_func(message: Any, targets: list[str]) -> list[str]:
            for case in cases:
                if isinstance(case, SwitchCaseEdgeGroupDefault):
                    return [case.target_id]
                try:
                    if case.condition(message):
                        return [case.target_id]
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("Error evaluating condition for case %s: %s", case.target_id, exc)
            raise RuntimeError("No matching case found in SwitchCaseEdgeGroup")

        target_ids = [case.target_id for case in cases]
        # Call FanOutEdgeGroup constructor directly to avoid type checking issues
        edges = [Edge(source_id=source_id, target_id=target) for target in target_ids]
        EdgeGroup.__init__(self, edges, id=id, type=self.__class__.__name__)

        # Initialize FanOutEdgeGroup-specific attributes
        self._target_ids = list(target_ids)  # type: ignore[attr-defined]
        self._selection_func = selection_func  # type: ignore[attr-defined]
        self.selection_func_name = None  # type: ignore[attr-defined]
        self.cases = list(cases)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the switch-case group, capturing all case descriptors.

        Each case is converted using `encode_value` to respect dataclass
        semantics as well as any nested serialisable structures.

        Examples:
            .. code-block:: python

                group = SwitchCaseEdgeGroup(
                    "router",
                    [
                        SwitchCaseEdgeGroupCase(lambda _: True, target_id="handler"),
                        SwitchCaseEdgeGroupDefault(target_id="fallback"),
                    ],
                )
                snapshot = group.to_dict()
                assert len(snapshot["cases"]) == 2
        """
        payload = super().to_dict()
        payload["cases"] = [encode_value(case) for case in self.cases]
        return payload


@EdgeGroup.register
@dataclass(init=False)
class InternalEdgeGroup(EdgeGroup):
    """Special edge group used to route internal messages to executors.

    This group is created automatically when a new executor is added to the workflow
    builder. It contains a single edge that routes messages from the internal source
    to the executor itself. Internal source represent messages that are generated by
    the system rather than by another executor. This includes request and response
    handling.

    This edge group only contains one edge from the internal source to the executor.
    And it does not support any conditions or complex routing logic.

    During workflow serialization and deserialization, the internal edge group is
    preserved and visible to systems consuming the workflow definition.

    Messages sent along this edge will also be captured by monitoring and logging systems,
    allowing for observability into internal message flows (when tracing is enabled).
    """

    def __init__(self, executor_id: str) -> None:
        """Create an internal edge group from the given edges.

        Parameters
        ----------
        executor_id:
            Identifier of the internal executor that should receive messages.

        Examples:
            .. code-block:: python

                edge_group = InternalEdgeGroup("executor_a")
        """
        edge = Edge(source_id=INTERNAL_SOURCE_ID(executor_id), target_id=executor_id)
        super().__init__([edge])
