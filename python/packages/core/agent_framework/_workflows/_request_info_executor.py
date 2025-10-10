# Copyright (c) Microsoft. All rights reserved.

import contextlib
import importlib
import json
import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from textwrap import shorten
from typing import Any, ClassVar, Generic, TypeVar, cast

from ._checkpoint import WorkflowCheckpoint
from ._events import (
    RequestInfoEvent,  # type: ignore[reportPrivateUsage]
)
from ._executor import Executor, handler
from ._runner_context import _decode_checkpoint_value  # type: ignore
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


@dataclass
class PendingRequestDetails:
    """Lightweight information about a pending request captured in a checkpoint."""

    request_id: str
    prompt: str | None = None
    draft: str | None = None
    iteration: int | None = None
    source_executor_id: str | None = None
    original_request: "RequestInfoMessage | dict[str, Any] | None" = None


@dataclass
class WorkflowCheckpointSummary:
    """Human-readable summary of a workflow checkpoint."""

    checkpoint_id: str
    iteration_count: int
    targets: list[str]
    executor_states: list[str]
    status: str
    draft_preview: str | None
    pending_requests: list[PendingRequestDetails]


@dataclass
class RequestInfoMessage:
    """Base class for all request messages in workflows.

    Any message that should be routed to the RequestInfoExecutor for external
    handling must inherit from this class. This ensures type safety and makes
    the request/response pattern explicit.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique identifier for correlating requests and responses."""

    source_executor_id: str | None = None
    """ID of the executor expecting a response to this request.
    May differ from the executor that sent the request if intercepted and forwarded."""


TRequest = TypeVar("TRequest", bound="RequestInfoMessage")
TResponse = TypeVar("TResponse")


@dataclass
class RequestResponse(Generic[TRequest, TResponse]):
    """Response type for request/response correlation in workflows.

    This type is used by RequestInfoExecutor to create correlated responses
    that include the original request context for proper message routing.
    """

    data: TResponse
    """The response data returned from handling the request."""

    original_request: TRequest
    """The original request that this response corresponds to."""

    request_id: str
    """The ID of the original request."""


# endregion: Request/Response Types


# region Request Info Executor
class RequestInfoExecutor(Executor):
    """Built-in executor that handles request/response patterns in workflows.

    This executor acts as a gateway for external information requests. When it receives
    a request message, it saves the request details and emits a RequestInfoEvent. When
    a response is provided externally, it emits the response as a message.
    """

    _PENDING_SHARED_STATE_KEY: ClassVar[str] = "_af_pending_request_info"

    def __init__(self, id: str):
        """Initialize the RequestInfoExecutor with a unique ID.

        Args:
            id: Unique ID for this RequestInfoExecutor.
        """
        super().__init__(id=id)
        self._request_events: dict[str, RequestInfoEvent] = {}

    @handler
    async def run(self, message: RequestInfoMessage, ctx: WorkflowContext) -> None:
        """Run the RequestInfoExecutor with the given message."""
        # Use source_executor_id from message if available, otherwise fall back to context
        source_executor_id = message.source_executor_id or ctx.get_source_executor_id()

        event = RequestInfoEvent(
            request_id=message.request_id,
            source_executor_id=source_executor_id,
            request_type=type(message),
            request_data=message,
        )
        self._request_events[message.request_id] = event
        await self._record_pending_request_snapshot(message, source_executor_id, ctx)
        await ctx.add_event(event)

    async def handle_response(
        self,
        response_data: Any,
        request_id: str,
        ctx: WorkflowContext[RequestResponse[RequestInfoMessage, Any]],
    ) -> None:
        """Handle a response to a request.

        Args:
            request_id: The ID of the request to which this response corresponds.
            response_data: The data returned in the response.
            ctx: The workflow context for sending the response.
        """
        event = self._request_events.get(request_id)
        if event is None:
            event = await self._rehydrate_request_event(request_id, ctx)
        if event is None:
            raise ValueError(f"No request found with ID: {request_id}")

        self._request_events.pop(request_id, None)

        # Create a correlated response that includes both the response data and original request
        if not isinstance(event.data, RequestInfoMessage):
            raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
        correlated_response = RequestResponse(data=response_data, original_request=event.data, request_id=request_id)
        await ctx.send_message(correlated_response, target_id=event.source_executor_id)

        await self._clear_pending_request_snapshot(request_id, ctx)

    async def _record_pending_request_snapshot(
        self,
        request: RequestInfoMessage,
        source_executor_id: str,
        ctx: WorkflowContext[Any],
    ) -> None:
        snapshot = self._build_request_snapshot(request, source_executor_id)

        pending = await self._load_pending_request_state(ctx)
        pending[request.request_id] = snapshot
        await self._persist_pending_request_state(pending, ctx)
        await self._write_executor_state(ctx, pending)

    async def _clear_pending_request_snapshot(self, request_id: str, ctx: WorkflowContext[Any]) -> None:
        pending = await self._load_pending_request_state(ctx)
        if request_id in pending:
            pending.pop(request_id, None)
            await self._persist_pending_request_state(pending, ctx)
        await self._write_executor_state(ctx, pending)

    async def _load_pending_request_state(self, ctx: WorkflowContext[Any]) -> dict[str, Any]:
        try:
            existing = await ctx.get_shared_state(self._PENDING_SHARED_STATE_KEY)
        except KeyError:
            return {}
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to read pending request state: {exc}")
            return {}

        if not isinstance(existing, dict):
            if existing not in (None, {}):
                logger.warning(
                    f"RequestInfoExecutor {self.id} encountered non-dict pending state "
                    f"({type(existing).__name__}); resetting."
                )
            return {}

        return dict(existing)  # type: ignore[arg-type]

    async def _persist_pending_request_state(self, pending: dict[str, Any], ctx: WorkflowContext[Any]) -> None:
        await self._safe_set_shared_state(ctx, pending)
        await self._safe_set_runner_state(ctx, pending)

    async def _safe_set_shared_state(self, ctx: WorkflowContext[Any], pending: dict[str, Any]) -> None:
        try:
            await ctx.set_shared_state(self._PENDING_SHARED_STATE_KEY, pending)
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to update shared pending state: {exc}")

    async def _safe_set_runner_state(self, ctx: WorkflowContext[Any], pending: dict[str, Any]) -> None:
        try:
            await ctx.set_state({"pending_requests": pending})
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to update runner state with pending requests: {exc}")

    def snapshot_state(self) -> dict[str, Any]:
        """Serialize pending requests so checkpoint restoration can resume seamlessly."""

        def _encode_event(event: RequestInfoEvent) -> dict[str, Any]:
            request_data = event.data
            payload: dict[str, Any]
            data_cls = request_data.__class__ if request_data is not None else type(None)

            payload = self._encode_request_payload(request_data, data_cls)

            return {
                "source_executor_id": event.source_executor_id,
                "request_type": f"{event.request_type.__module__}:{event.request_type.__qualname__}",
                "request_data": payload,
            }

        return {
            "request_events": {rid: _encode_event(event) for rid, event in self._request_events.items()},
        }

    def _encode_request_payload(self, request_data: RequestInfoMessage | None, data_cls: type[Any]) -> dict[str, Any]:
        if request_data is None or isinstance(request_data, (str, int, float, bool)):
            return {
                "kind": "raw",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": request_data,
            }

        if is_dataclass(request_data) and not isinstance(request_data, type):
            dataclass_instance = cast(Any, request_data)
            safe_value = self._make_json_safe(asdict(dataclass_instance))
            return {
                "kind": "dataclass",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": safe_value,
            }

        to_dict_fn = getattr(request_data, "to_dict", None)
        if callable(to_dict_fn):
            try:
                dumped = to_dict_fn()
            except TypeError:
                dumped = to_dict_fn()
            safe_value = self._make_json_safe(dumped)
            return {
                "kind": "dict",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": safe_value,
            }

        to_json_fn = getattr(request_data, "to_json", None)
        if callable(to_json_fn):
            try:
                dumped = to_json_fn()
            except TypeError:
                dumped = to_json_fn()
            converted = dumped
            if isinstance(dumped, (str, bytes, bytearray)):
                decoded: str | bytes | bytearray
                if isinstance(dumped, (bytes, bytearray)):
                    try:
                        decoded = dumped.decode()
                    except Exception:
                        decoded = dumped
                else:
                    decoded = dumped
                try:
                    converted = json.loads(decoded)
                except Exception:
                    converted = decoded
            safe_value = self._make_json_safe(converted)
            return {
                "kind": "dict" if isinstance(converted, dict) else "json",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": safe_value,
            }

        details = self._serialise_request_details(request_data)
        if details is not None:
            safe_value = self._make_json_safe(details)
            return {
                "kind": "raw",
                "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
                "value": safe_value,
            }

        safe_value = self._make_json_safe(request_data)
        return {
            "kind": "raw",
            "type": f"{data_cls.__module__}:{data_cls.__qualname__}",
            "value": safe_value,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore pending request bookkeeping from checkpoint state."""
        self._request_events.clear()
        stored_events = state.get("request_events", {})

        for request_id, payload in stored_events.items():
            request_type_qual = payload.get("request_type", "")
            try:
                request_type = self._import_qualname(request_type_qual)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.debug(
                    "RequestInfoExecutor %s failed to import %s during restore: %s",
                    self.id,
                    request_type_qual,
                    exc,
                )
                request_type = RequestInfoMessage
            request_data_meta = payload.get("request_data", {})
            request_data = self._decode_request_data(request_data_meta)
            event = RequestInfoEvent(
                request_id=request_id,
                source_executor_id=payload.get("source_executor_id", ""),
                request_type=request_type,
                request_data=request_data,
            )
            self._request_events[request_id] = event

    @staticmethod
    def _import_qualname(qualname: str) -> type[Any]:
        module_name, _, type_name = qualname.partition(":")
        if not module_name or not type_name:
            raise ValueError(f"Invalid qualified name: {qualname}")
        module = importlib.import_module(module_name)
        attr: Any = module
        for part in type_name.split("."):
            attr = getattr(attr, part)
        if not isinstance(attr, type):
            raise TypeError(f"Resolved object is not a type: {qualname}")
        return attr

    def _decode_request_data(self, metadata: dict[str, Any]) -> RequestInfoMessage:
        kind = metadata.get("kind")
        type_name = metadata.get("type", "")
        value: Any = metadata.get("value", {})
        if type_name:
            try:
                imported = self._import_qualname(type_name)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.debug(
                    "RequestInfoExecutor %s failed to import %s during decode: %s",
                    self.id,
                    type_name,
                    exc,
                )
                imported = RequestInfoMessage
        else:
            imported = RequestInfoMessage
        target_cls: type[RequestInfoMessage]
        if isinstance(imported, type) and issubclass(imported, RequestInfoMessage):
            target_cls = imported
        else:
            target_cls = RequestInfoMessage

        if kind == "dataclass" and isinstance(value, dict):
            with contextlib.suppress(TypeError):
                return target_cls(**value)  # type: ignore[arg-type]

        # Backwards-compat handling for checkpoints that used to store pydantic as "dict"
        if kind in {"dict", "pydantic", "json"} and isinstance(value, dict):
            from_dict = getattr(target_cls, "from_dict", None)
            if callable(from_dict):
                with contextlib.suppress(Exception):
                    return cast(RequestInfoMessage, from_dict(value))

        if kind == "json" and isinstance(value, str):
            from_json = getattr(target_cls, "from_json", None)
            if callable(from_json):
                with contextlib.suppress(Exception):
                    return cast(RequestInfoMessage, from_json(value))
            with contextlib.suppress(Exception):
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return self._decode_request_data({"kind": "dict", "type": type_name, "value": parsed})

        if isinstance(value, dict):
            with contextlib.suppress(TypeError):
                return target_cls(**value)  # type: ignore[arg-type]
            instance = object.__new__(target_cls)
            instance.__dict__.update(value)  # type: ignore[arg-type]
            return instance

        with contextlib.suppress(Exception):
            return target_cls()
        return RequestInfoMessage()

    async def _write_executor_state(self, ctx: WorkflowContext[Any], pending: dict[str, Any]) -> None:
        state = self.snapshot_state()
        state["pending_requests"] = pending
        try:
            await ctx.set_state(state)
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to persist executor state: {exc}")

    def _build_request_snapshot(
        self,
        request: RequestInfoMessage,
        source_executor_id: str,
    ) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "request_id": request.request_id,
            "source_executor_id": source_executor_id,
            "request_type": f"{type(request).__module__}:{type(request).__name__}",
            "summary": repr(request),
        }

        details = self._serialise_request_details(request)
        if details:
            snapshot["details"] = details
            for key in ("prompt", "draft", "iteration"):
                if key in details and key not in snapshot:
                    snapshot[key] = details[key]

        return snapshot

    def _serialise_request_details(self, request: RequestInfoMessage) -> dict[str, Any] | None:
        if is_dataclass(request):
            data = self._make_json_safe(asdict(request))
            if isinstance(data, dict):
                return cast(dict[str, Any], data)
            return None

        to_dict = getattr(request, "to_dict", None)
        if callable(to_dict):
            try:
                dump = self._make_json_safe(to_dict())
            except TypeError:
                dump = self._make_json_safe(to_dict())
            if isinstance(dump, dict):
                return cast(dict[str, Any], dump)
            return None

        to_json = getattr(request, "to_json", None)
        if callable(to_json):
            try:
                raw = to_json()
            except TypeError:
                raw = to_json()
            converted = raw
            if isinstance(raw, (str, bytes, bytearray)):
                decoded: str | bytes | bytearray
                if isinstance(raw, (bytes, bytearray)):
                    try:
                        decoded = raw.decode()
                    except Exception:
                        decoded = raw
                else:
                    decoded = raw
                try:
                    converted = json.loads(decoded)
                except Exception:
                    converted = decoded
            dump = self._make_json_safe(converted)
            if isinstance(dump, dict):
                return cast(dict[str, Any], dump)
            return None

        attrs = getattr(request, "__dict__", None)
        if isinstance(attrs, dict):
            cleaned = self._make_json_safe(attrs)
            if isinstance(cleaned, dict):
                return cast(dict[str, Any], cleaned)

        return None

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            safe_dict: dict[str, Any] = {}
            for key, val in value.items():  # type: ignore[attr-defined]
                safe_dict[str(key)] = self._make_json_safe(val)  # type: ignore[arg-type]
            return safe_dict
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self._make_json_safe(item) for item in value]  # type: ignore[misc]
        return repr(value)

    async def has_pending_request(self, request_id: str, ctx: WorkflowContext[Any]) -> bool:
        if request_id in self._request_events:
            return True
        snapshot = await self._get_pending_request_snapshot(request_id, ctx)
        return snapshot is not None

    async def _rehydrate_request_event(
        self,
        request_id: str,
        ctx: WorkflowContext[Any],
    ) -> RequestInfoEvent | None:
        snapshot = await self._get_pending_request_snapshot(request_id, ctx)
        if snapshot is None:
            return None

        source_executor_id = snapshot.get("source_executor_id")
        if not isinstance(source_executor_id, str) or not source_executor_id:
            return None

        request = self._construct_request_from_snapshot(snapshot)
        if request is None:
            return None

        event = RequestInfoEvent(
            request_id=request_id,
            source_executor_id=source_executor_id,
            request_type=type(request),
            request_data=request,
        )
        self._request_events[request_id] = event
        return event

    async def _get_pending_request_snapshot(self, request_id: str, ctx: WorkflowContext[Any]) -> dict[str, Any] | None:
        pending = await self._collect_pending_request_snapshots(ctx)
        snapshot = pending.get(request_id)
        if snapshot is None:
            return None
        return snapshot

    async def _collect_pending_request_snapshots(self, ctx: WorkflowContext[Any]) -> dict[str, dict[str, Any]]:
        combined: dict[str, dict[str, Any]] = {}

        try:
            shared_pending = await ctx.get_shared_state(self._PENDING_SHARED_STATE_KEY)
        except KeyError:
            shared_pending = None
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to read shared pending state during rehydrate: {exc}")
            shared_pending = None

        if isinstance(shared_pending, dict):
            for key, value in shared_pending.items():  # type: ignore[attr-defined]
                if isinstance(key, str) and isinstance(value, dict):
                    combined[key] = cast(dict[str, Any], value)

        try:
            state = await ctx.get_state()
        except Exception as exc:  # pragma: no cover - transport specific
            logger.warning(f"RequestInfoExecutor {self.id} failed to read runner state during rehydrate: {exc}")
            state = None

        if isinstance(state, dict):
            state_pending = state.get("pending_requests")
            if isinstance(state_pending, dict):
                for key, value in state_pending.items():  # type: ignore[attr-defined]
                    if isinstance(key, str) and isinstance(value, dict) and key not in combined:
                        combined[key] = cast(dict[str, Any], value)

        return combined

    def _construct_request_from_snapshot(self, snapshot: dict[str, Any]) -> RequestInfoMessage | None:
        details_raw = snapshot.get("details")
        details: dict[str, Any] = cast(dict[str, Any], details_raw) if isinstance(details_raw, dict) else {}

        request_cls: type[RequestInfoMessage] = RequestInfoMessage
        request_type_str = snapshot.get("request_type")
        if isinstance(request_type_str, str) and ":" in request_type_str:
            module_name, class_name = request_type_str.split(":", 1)
            try:
                module = importlib.import_module(module_name)
                candidate = getattr(module, class_name)
                if isinstance(candidate, type) and issubclass(candidate, RequestInfoMessage):
                    request_cls = candidate
            except Exception as exc:
                logger.warning(f"RequestInfoExecutor {self.id} could not import {module_name}.{class_name}: {exc}")
                request_cls = RequestInfoMessage

        request: RequestInfoMessage | None = self._instantiate_request(request_cls, details)

        if request is None and request_cls is not RequestInfoMessage:
            request = self._instantiate_request(RequestInfoMessage, details)

        if request is None:
            logger.warning(
                f"RequestInfoExecutor {self.id} could not reconstruct request "
                f"{request_type_str or RequestInfoMessage.__name__} from snapshot keys {sorted(details.keys())}"
            )
            return None

        for key, value in details.items():
            if key == "request_id":
                continue
            try:
                setattr(request, key, value)
            except Exception as exc:
                logger.debug(
                    f"RequestInfoExecutor {self.id} could not set attribute {key} on {type(request).__name__}: {exc}"
                )
                continue

        snapshot_request_id = snapshot.get("request_id")
        if isinstance(snapshot_request_id, str) and snapshot_request_id:
            try:
                request.request_id = snapshot_request_id
            except Exception as exc:
                logger.debug(
                    f"RequestInfoExecutor {self.id} could not apply snapshot "
                    f"request_id to {type(request).__name__}: {exc}"
                )

        return request

    def _instantiate_request(
        self,
        request_cls: type[RequestInfoMessage],
        details: dict[str, Any],
    ) -> RequestInfoMessage | None:
        try:
            from_dict = getattr(request_cls, "from_dict", None)
            if callable(from_dict):
                return cast(RequestInfoMessage, from_dict(details))
        except (TypeError, ValueError) as exc:
            logger.debug(f"RequestInfoExecutor {self.id} failed to hydrate {request_cls.__name__} via from_dict: {exc}")
        except Exception as exc:
            logger.warning(
                f"RequestInfoExecutor {self.id} encountered unexpected error during "
                f"{request_cls.__name__}.from_dict: {exc}"
            )

        if is_dataclass(request_cls):
            try:
                field_names = {f.name for f in fields(request_cls)}
                ctor_kwargs = {name: details[name] for name in field_names if name in details}
                return request_cls(**ctor_kwargs)
            except (TypeError, ValueError) as exc:
                logger.debug(
                    f"RequestInfoExecutor {self.id} could not instantiate dataclass "
                    f"{request_cls.__name__} with snapshot data: {exc}"
                )
            except Exception as exc:
                logger.warning(
                    f"RequestInfoExecutor {self.id} encountered unexpected error "
                    f"constructing dataclass {request_cls.__name__}: {exc}"
                )

        try:
            instance = request_cls()
        except Exception as exc:
            logger.warning(
                f"RequestInfoExecutor {self.id} could not instantiate {request_cls.__name__} without arguments: {exc}"
            )
            return None

        for key, value in details.items():
            if key == "request_id":
                continue
            try:
                setattr(instance, key, value)
            except Exception as exc:
                logger.debug(
                    f"RequestInfoExecutor {self.id} could not set attribute {key} on "
                    f"{request_cls.__name__} during instantiation: {exc}"
                )
                continue

        return instance

    @staticmethod
    def pending_requests_from_checkpoint(
        checkpoint: WorkflowCheckpoint,
        *,
        request_executor_ids: Iterable[str] | None = None,
    ) -> list[PendingRequestDetails]:
        executor_filter: set[str] | None = None
        if request_executor_ids is not None:
            executor_filter = {str(value) for value in request_executor_ids}

        pending: dict[str, PendingRequestDetails] = {}

        shared_map = checkpoint.shared_state.get(RequestInfoExecutor._PENDING_SHARED_STATE_KEY)
        if isinstance(shared_map, Mapping):
            for request_id, snapshot in shared_map.items():  # type: ignore[attr-defined]
                RequestInfoExecutor._merge_snapshot(pending, str(request_id), snapshot)  # type: ignore[arg-type]

        for state in checkpoint.executor_states.values():
            if not isinstance(state, Mapping):
                continue
            inner = state.get("pending_requests")
            if isinstance(inner, Mapping):
                for request_id, snapshot in inner.items():  # type: ignore[attr-defined]
                    RequestInfoExecutor._merge_snapshot(pending, str(request_id), snapshot)  # type: ignore[arg-type]

        for source_id, message_list in checkpoint.messages.items():
            if executor_filter is not None and source_id not in executor_filter:
                continue
            if not isinstance(message_list, list):
                continue
            for message in message_list:
                if not isinstance(message, Mapping):
                    continue
                payload = _decode_checkpoint_value(message.get("data"))
                RequestInfoExecutor._merge_message_payload(pending, payload, message)

        return list(pending.values())

    @staticmethod
    def checkpoint_summary(
        checkpoint: WorkflowCheckpoint,
        *,
        request_executor_ids: Iterable[str] | None = None,
        preview_width: int = 70,
    ) -> WorkflowCheckpointSummary:
        targets = sorted(checkpoint.messages.keys())
        executor_states = sorted(checkpoint.executor_states.keys())
        pending = RequestInfoExecutor.pending_requests_from_checkpoint(
            checkpoint, request_executor_ids=request_executor_ids
        )

        draft_preview: str | None = None
        for entry in pending:
            if entry.draft:
                draft_preview = shorten(entry.draft, width=preview_width, placeholder="…")
                break

        status = "idle"
        if pending:
            status = "awaiting human response"
        elif not checkpoint.messages and "finalise" in executor_states:
            status = "completed"
        elif checkpoint.messages:
            status = "awaiting next superstep"
        elif request_executor_ids is not None and any(tid in targets for tid in request_executor_ids):
            status = "awaiting request delivery"

        return WorkflowCheckpointSummary(
            checkpoint_id=checkpoint.checkpoint_id,
            iteration_count=checkpoint.iteration_count,
            targets=targets,
            executor_states=executor_states,
            status=status,
            draft_preview=draft_preview,
            pending_requests=pending,
        )

    @staticmethod
    def _merge_snapshot(
        pending: dict[str, PendingRequestDetails],
        request_id: str,
        snapshot: Any,
    ) -> None:
        if not request_id or not isinstance(snapshot, Mapping):
            return

        details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))

        RequestInfoExecutor._apply_update(
            details,
            prompt=snapshot.get("prompt"),  # type: ignore[attr-defined]
            draft=snapshot.get("draft"),  # type: ignore[attr-defined]
            iteration=snapshot.get("iteration"),  # type: ignore[attr-defined]
            source_executor_id=snapshot.get("source_executor_id"),  # type: ignore[attr-defined]
        )

        extra = snapshot.get("details")  # type: ignore[attr-defined]
        if isinstance(extra, Mapping):
            RequestInfoExecutor._apply_update(
                details,
                prompt=extra.get("prompt"),  # type: ignore[attr-defined]
                draft=extra.get("draft"),  # type: ignore[attr-defined]
                iteration=extra.get("iteration"),  # type: ignore[attr-defined]
            )

    @staticmethod
    def _merge_message_payload(
        pending: dict[str, PendingRequestDetails],
        payload: Any,
        raw_message: Mapping[str, Any],
    ) -> None:
        if isinstance(payload, RequestResponse):
            request_id = payload.request_id or RequestInfoExecutor._get_field(payload.original_request, "request_id")  # type: ignore[arg-type]
            if not request_id:
                return
            details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))
            RequestInfoExecutor._apply_update(
                details,
                prompt=RequestInfoExecutor._get_field(payload.original_request, "prompt"),  # type: ignore[arg-type]
                draft=RequestInfoExecutor._get_field(payload.original_request, "draft"),  # type: ignore[arg-type]
                iteration=RequestInfoExecutor._get_field(payload.original_request, "iteration"),  # type: ignore[arg-type]
                source_executor_id=raw_message.get("source_id"),
                original_request=payload.original_request,  # type: ignore[arg-type]
            )
        elif isinstance(payload, RequestInfoMessage):
            request_id = getattr(payload, "request_id", None)
            if not request_id:
                return
            details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))
            RequestInfoExecutor._apply_update(
                details,
                prompt=getattr(payload, "prompt", None),
                draft=getattr(payload, "draft", None),
                iteration=getattr(payload, "iteration", None),
                source_executor_id=raw_message.get("source_id"),
                original_request=payload,
            )

    @staticmethod
    def _apply_update(
        details: PendingRequestDetails,
        *,
        prompt: Any = None,
        draft: Any = None,
        iteration: Any = None,
        source_executor_id: Any = None,
        original_request: Any = None,
    ) -> None:
        if prompt and not details.prompt:
            details.prompt = str(prompt)
        if draft and not details.draft:
            details.draft = str(draft)
        if iteration is not None and details.iteration is None:
            coerced = RequestInfoExecutor._coerce_int(iteration)
            if coerced is not None:
                details.iteration = coerced
        if source_executor_id and not details.source_executor_id:
            details.source_executor_id = str(source_executor_id)
        if original_request is not None and details.original_request is None:
            details.original_request = original_request

    @staticmethod
    def _get_field(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, Mapping):
            return obj.get(key)  # type: ignore[attr-defined,return-value]
        return getattr(obj, key, None)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
