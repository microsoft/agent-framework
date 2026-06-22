# Copyright (c) Microsoft. All rights reserved.

"""Foundry Hosted Agent history provider."""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable, Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from importlib import import_module
from typing import Any, ClassVar, cast

from agent_framework import ExperimentalFeature, HistoryProvider, Message
from agent_framework._feature_stage import experimental
from azure.ai.agentserver.core import AgentConfig
from azure.ai.agentserver.responses import (
    FoundryStorageProvider,
    FoundryStorageSettings,
    InMemoryResponseProvider,
    IsolationContext,
)
from azure.ai.agentserver.responses._id_generator import IdGenerator
from azure.ai.agentserver.responses.models import (
    MessageContentInputTextContent,
    MessageContentOutputTextContent,
    OutputItem,
    OutputItemMessage,
    OutputItemOutputMessage,
    ResponseObject,
)
from azure.core.credentials_async import AsyncTokenCredential

from ._responses import _output_items_to_messages  # pyright: ignore[reportPrivateUsage]

FoundryResponseIdFactory = Callable[[str | None], str]
_FOUNDRY_PROJECT_ENDPOINT = "FOUNDRY_PROJECT_ENDPOINT"


@dataclass(frozen=True)
class _RequestContext:
    response_id: str
    previous_response_id: str | None = None


_request_context: ContextVar[_RequestContext | None] = ContextVar(
    "agent_framework_foundry_hosting_request_context",
    default=None,
)


@experimental(feature_id=ExperimentalFeature.HOSTING)
def foundry_response_id(previous_response_id: str | None = None) -> str:
    """Mint a Foundry-storage-compatible response ID.

    Args:
        previous_response_id: Optional previous response ID. When it already uses
            the Foundry response ID shape, the new ID reuses its partition key so
            chained responses are stored together.

    Returns:
        A response ID that the Foundry Hosted Agents storage backend accepts.
    """
    return IdGenerator.new_response_id(previous_response_id or "")


@experimental(feature_id=ExperimentalFeature.HOSTING)
def foundry_response_id_factory() -> FoundryResponseIdFactory:
    """Return a callable suitable for response ID factory hooks.

    Returns:
        The :func:`foundry_response_id` function.
    """
    return foundry_response_id


def _current_request_context() -> _RequestContext | None:
    return _request_context.get()


def _current_isolation() -> IsolationContext | None:
    """Read host-bound Foundry isolation keys without depending on hosting at import time."""
    try:
        module = import_module("agent_framework_hosting")
    except ImportError:
        return None

    get_current_isolation_keys = getattr(module, "get_current_isolation_keys", None)
    if not callable(get_current_isolation_keys):
        return None
    keys = get_current_isolation_keys()
    if keys is None or bool(getattr(keys, "is_empty", True)):
        return None
    user_key = getattr(keys, "user_key", None)
    chat_key = getattr(keys, "chat_key", None)
    return IsolationContext(
        user_key=user_key if isinstance(user_key, str) else None,
        chat_key=chat_key if isinstance(chat_key, str) else None,
    )


def _text_for_message(message: Message) -> str:
    return message.text or ""


def _message_to_item(message: Message, *, response_id: str) -> OutputItem:
    text = _text_for_message(message)
    if message.role in {"user", "system", "developer"}:
        return OutputItemMessage({
            "id": IdGenerator.new_message_item_id(response_id),
            "type": "message",
            "role": message.role,
            "content": [MessageContentInputTextContent({"type": "input_text", "text": text}).as_dict()],
        })

    return OutputItemOutputMessage({
        "id": IdGenerator.new_output_message_item_id(response_id),
        "type": "output_message",
        "role": "assistant",
        "status": "completed",
        "content": [
            MessageContentOutputTextContent({"type": "output_text", "text": text, "annotations": []}).as_dict()
        ],
    })


@experimental(feature_id=ExperimentalFeature.HOSTING)
class FoundryHostedAgentHistoryProvider(HistoryProvider):
    """Conversation history provider backed by Foundry Hosted Agents storage.

    The provider uses Foundry storage in a hosted environment and an in-memory
    Foundry-compatible store for local development. Hosts can call
    :meth:`bind_request_context` around an agent run to align stored response IDs
    with the response ID returned to the client.

    Keyword Args:
        credential: Async token credential for Foundry storage. Required when running hosted.
        endpoint: Foundry project endpoint. Defaults to ``FOUNDRY_PROJECT_ENDPOINT``.
        history_limit: Maximum number of history item IDs to load per request.
        source_id: Unique context-provider source ID.
        load_messages: Whether history is loaded before invocation.
        store_inputs: Whether input messages are stored after invocation.
        store_context_messages: Whether context-provider messages are stored after invocation.
        store_context_from: Optional source IDs to store context messages from.
        store_outputs: Whether output messages are stored after invocation.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "foundry_hosted_agent"

    def __init__(
        self,
        *,
        credential: AsyncTokenCredential | None = None,
        endpoint: str | None = None,
        history_limit: int = 100,
        source_id: str = DEFAULT_SOURCE_ID,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        store_outputs: bool = True,
    ) -> None:
        super().__init__(
            source_id=source_id,
            load_messages=load_messages,
            store_inputs=store_inputs,
            store_context_messages=store_context_messages,
            store_context_from=store_context_from,
            store_outputs=store_outputs,
        )
        self._credential = credential
        self._endpoint = endpoint or os.environ.get(_FOUNDRY_PROJECT_ENDPOINT)
        self._history_limit = history_limit
        self._backend: FoundryStorageProvider | InMemoryResponseProvider | None = None

    @staticmethod
    def is_hosted_environment() -> bool:
        """Return whether the current process is running as a Foundry Hosted Agent."""
        return AgentConfig.from_env().is_hosted

    @contextmanager
    def bind_request_context(
        self,
        *,
        response_id: str,
        previous_response_id: str | None = None,
        **_kwargs: Any,
    ) -> Generator[None]:
        """Bind response-chain anchors for one agent run.

        Args:
            response_id: Response ID to use for the storage write from this run.
            previous_response_id: Optional previous response ID to load and chain.
            **_kwargs: Ignored extension values from host request attributes.
        """
        token = _request_context.set(_RequestContext(response_id, previous_response_id))
        try:
            yield
        finally:
            _request_context.reset(token)

    def _resolve_backend(self) -> FoundryStorageProvider | InMemoryResponseProvider:
        if self._backend is not None:
            return self._backend

        if self.is_hosted_environment():
            if self._credential is None:
                raise RuntimeError("FoundryHostedAgentHistoryProvider requires credential=... when hosted.")
            if not self._endpoint:
                raise RuntimeError(
                    "FoundryHostedAgentHistoryProvider requires endpoint=... or FOUNDRY_PROJECT_ENDPOINT when hosted."
                )
            self._backend = FoundryStorageProvider(
                credential=self._credential,
                settings=FoundryStorageSettings.from_endpoint(self._endpoint),
            )
        else:
            self._backend = InMemoryResponseProvider()
        return self._backend

    async def aclose(self) -> None:
        """Close the underlying storage provider when it exposes ``aclose``."""
        if self._backend is None:
            return
        aclose = getattr(self._backend, "aclose", None)
        if callable(aclose):
            await cast(Callable[[], Awaitable[None]], aclose)()
        self._backend = None

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        """Load messages for the current response chain."""
        del state
        context = _current_request_context()
        anchor = context.previous_response_id if context is not None else session_id
        if not anchor:
            return []

        isolation = cast(IsolationContext | None, kwargs.get("isolation")) or _current_isolation()
        backend = self._resolve_backend()
        item_ids = await backend.get_history_item_ids(anchor, None, self._history_limit, isolation=isolation)
        if not item_ids:
            return []

        items = await backend.get_items(item_ids, isolation=isolation)
        return await _output_items_to_messages([item for item in items if item is not None])

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Persist messages for the current response chain."""
        del state
        if not messages:
            return

        context = _current_request_context()
        response_id = context.response_id if context is not None else foundry_response_id(session_id)
        previous_response_id = context.previous_response_id if context is not None else session_id
        isolation = cast(IsolationContext | None, kwargs.get("isolation")) or _current_isolation()

        items = [_message_to_item(message, response_id=response_id) for message in messages]
        input_items = [item for item in items if item.type == "message"]
        output_items = [item for item in items if item.type != "message"]

        history_item_ids = (
            await self._resolve_backend().get_history_item_ids(
                previous_response_id,
                None,
                self._history_limit,
                isolation=isolation,
            )
            if previous_response_id
            else None
        )
        now = int(time.time())
        response_body: dict[str, Any] = {
            "id": response_id,
            "response_id": response_id,
            "object": "response",
            "background": False,
            "parallel_tool_calls": False,
            "instructions": "",
            "output": [item.as_dict() for item in output_items],
            "created_at": now,
            "agent_reference": {"type": "agent_reference", "name": os.environ.get("FOUNDRY_AGENT_NAME", "agent")},
            "status": "completed",
            "completed_at": now,
        }
        if previous_response_id:
            response_body["previous_response_id"] = previous_response_id
        model_deployment = os.environ.get("MODEL_DEPLOYMENT_NAME") or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        if model_deployment:
            response_body["model"] = model_deployment
        agent_session_id = os.environ.get("FOUNDRY_AGENT_SESSION_ID")
        if agent_session_id:
            response_body["agent_session_id"] = agent_session_id

        await self._resolve_backend().create_response(
            ResponseObject(response_body),
            input_items=input_items,
            history_item_ids=history_item_ids,
            isolation=isolation,
        )
