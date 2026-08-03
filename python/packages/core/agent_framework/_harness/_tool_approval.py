# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import copy
import inspect
import json
from asyncio import sleep
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable, Mapping, MutableMapping, Sequence
from typing import Any, Literal, cast

from .._middleware import AgentContext, AgentMiddleware
from .._serialization import SerializationMixin
from .._sessions import AgentSession
from .._telemetry import FeatureIndex, mark_feature_used
from .._types import (
    AgentResponse,
    AgentResponseUpdate,
    Content,
    FinishReason,
    FinishReasonLiteral,
    Message,
    ResponseStream,
)

DEFAULT_TOOL_APPROVAL_SOURCE_ID = "tool_approval"
_FUNCTION_INVOCATION_BUDGET_STATE_KEY = "_function_invocation_budget_state"
ALWAYS_APPROVE_PROPERTY = "tool_approval"
ALWAYS_APPROVE_SCOPE_PROPERTY = "always_approve"
ALWAYS_APPROVE_TOOL: Literal["tool"] = "tool"
ALWAYS_APPROVE_TOOL_WITH_ARGUMENTS: Literal["tool_with_arguments"] = "tool_with_arguments"

_RULES_KEY = "rules"
_QUEUED_APPROVAL_REQUESTS_KEY = "queued_approval_requests"
_COLLECTED_APPROVAL_RESPONSES_KEY = "collected_approval_responses"

ToolApprovalScope = Literal["tool", "tool_with_arguments"]
ToolApprovalRuleCallback = Callable[[Content], bool | Awaitable[bool]]


def _parse_function_arguments(function_call: Content) -> dict[str, Any]:
    arguments = function_call.parse_arguments()
    return dict(arguments or {})


def _serialize_argument_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _serialize_arguments(function_call: Content) -> dict[str, str]:
    """Serialize arguments for exact matching.

    ``None`` is reserved on :class:`ToolApprovalRule` for tool-wide rules.
    An argument-scoped rule for a no-argument call stores ``{}``, so it only
    matches future no-argument calls and never becomes a wildcard.
    """
    arguments = _parse_function_arguments(function_call)
    return {key: _serialize_argument_value(value) for key, value in arguments.items()}


def _server_label(function_call: Content) -> str | None:
    """Return the hosted-tool server boundary for a function call, if present."""
    value = function_call.additional_properties.get("server_label")
    return value if isinstance(value, str) else None


def _content_from_state(value: Any) -> Content:
    if isinstance(value, Content):
        return value
    if isinstance(value, Mapping):
        return Content.from_dict(cast(Mapping[str, Any], value))
    raise TypeError(f"Expected Content or mapping state item, got {type(value).__name__}.")


def _contents_from_state(values: Any) -> list[Content]:
    if not isinstance(values, list):
        return []
    state_items = list(cast(Iterable[Any], values))
    return [_content_from_state(value) for value in state_items]


def _content_to_state(content: Content) -> dict[str, Any]:
    return content.to_dict()


class ToolApprovalRule(SerializationMixin):
    """A standing rule for approving future matching tool calls."""

    tool_name: str
    arguments: dict[str, str] | None
    server_label: str | None

    def __init__(
        self,
        tool_name: str,
        arguments: Mapping[str, str] | None = None,
        *,
        server_label: str | None = None,
    ) -> None:
        """Initialize a tool approval rule.

        Args:
            tool_name: The function tool name this rule applies to.
            arguments: Optional canonicalized argument values. When omitted, the
                rule applies to every call to the tool. Use an empty mapping to
                match only no-argument calls.

        Keyword Args:
            server_label: Optional hosted-tool server boundary. Hosted approvals
                only match future approvals from the same server label.
        """
        normalized_name = tool_name.strip()
        if not normalized_name:
            raise ValueError("Tool approval rule tool_name must be a non-empty string.")
        self.tool_name = normalized_name
        self.arguments = dict(arguments) if arguments is not None else None
        self.server_label = server_label

    @classmethod
    def from_dict(
        cls,
        value: MutableMapping[str, Any],
        /,
        *,
        dependencies: MutableMapping[str, Any] | None = None,
    ) -> ToolApprovalRule:
        """Create a rule from serialized state."""
        del dependencies
        tool_name = value.get("tool_name")
        if not isinstance(tool_name, str):
            raise ValueError("Tool approval rule tool_name must be a string.")
        raw_arguments = value.get("arguments")
        if raw_arguments is not None and not isinstance(raw_arguments, Mapping):
            raise ValueError("Tool approval rule arguments must be a mapping or None.")
        server_label = value.get("server_label")
        if server_label is not None and not isinstance(server_label, str):
            raise ValueError("Tool approval rule server_label must be a string or None.")
        arguments = (
            {str(key): str(argument_value) for key, argument_value in cast(Mapping[str, Any], raw_arguments).items()}
            if isinstance(raw_arguments, Mapping)
            else None
        )
        return cls(tool_name=tool_name, arguments=arguments, server_label=server_label)

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Serialize the rule."""
        exclude = exclude or set()
        payload: dict[str, Any] = {"tool_name": self.tool_name}
        if "type" not in exclude:
            payload["type"] = self._get_type_identifier()
        if self.arguments is not None or not exclude_none:
            payload["arguments"] = self.arguments
        if self.server_label is not None or not exclude_none:
            payload["server_label"] = self.server_label
        return payload


class ToolApprovalState(SerializationMixin):
    """Session-backed state used by :class:`ToolApprovalMiddleware`."""

    rules: list[ToolApprovalRule]
    queued_approval_requests: list[Content]
    collected_approval_responses: list[Content]

    def __init__(
        self,
        *,
        rules: Sequence[ToolApprovalRule | Mapping[str, Any]] | None = None,
        queued_approval_requests: Sequence[Content | Mapping[str, Any]] | None = None,
        collected_approval_responses: Sequence[Content | Mapping[str, Any]] | None = None,
    ) -> None:
        """Initialize approval state."""
        self.rules = [
            rule if isinstance(rule, ToolApprovalRule) else ToolApprovalRule.from_dict(dict(rule))
            for rule in (rules or [])
        ]
        self.queued_approval_requests = [
            item if isinstance(item, Content) else Content.from_dict(item) for item in (queued_approval_requests or [])
        ]
        self.collected_approval_responses = [
            item if isinstance(item, Content) else Content.from_dict(item)
            for item in (collected_approval_responses or [])
        ]

    @classmethod
    def from_dict(
        cls,
        value: MutableMapping[str, Any],
        /,
        *,
        dependencies: MutableMapping[str, Any] | None = None,
    ) -> ToolApprovalState:
        """Create state from serialized state."""
        del dependencies
        return cls(
            rules=cast(Sequence[Mapping[str, Any]], value.get("rules", [])),
            queued_approval_requests=cast(Sequence[Mapping[str, Any]], value.get("queued_approval_requests", [])),
            collected_approval_responses=cast(
                Sequence[Mapping[str, Any]],
                value.get("collected_approval_responses", []),
            ),
        )

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Serialize state."""
        del exclude_none
        exclude = exclude or set()
        payload: dict[str, Any] = {
            "rules": [rule.to_dict() for rule in self.rules],
            "queued_approval_requests": [_content_to_state(item) for item in self.queued_approval_requests],
            "collected_approval_responses": [_content_to_state(item) for item in self.collected_approval_responses],
        }
        if "type" not in exclude:
            payload["type"] = self._get_type_identifier()
        return payload


def create_always_approve_tool_response(request: Content, *, reason: str | None = None) -> Content:
    """Create an approval response that records a standing rule for the whole tool.

    Args:
        request: The ``function_approval_request`` content to approve.

    Keyword Args:
        reason: Optional approval reason stored in ``additional_properties``.

    Returns:
        A ``function_approval_response`` with metadata consumed by
        :class:`ToolApprovalMiddleware`.
    """
    return _create_always_approve_response(request, ALWAYS_APPROVE_TOOL, reason=reason)


def create_always_approve_tool_with_arguments_response(request: Content, *, reason: str | None = None) -> Content:
    """Create an approval response that records a standing rule for the tool and exact arguments."""
    return _create_always_approve_response(request, ALWAYS_APPROVE_TOOL_WITH_ARGUMENTS, reason=reason)


def _create_always_approve_response(request: Content, scope: ToolApprovalScope, *, reason: str | None) -> Content:
    response = request.to_function_approval_response(approved=True)
    metadata: dict[str, Any] = {ALWAYS_APPROVE_SCOPE_PROPERTY: scope}
    if reason is not None:
        metadata["reason"] = reason
    response.additional_properties[ALWAYS_APPROVE_PROPERTY] = metadata
    return response


def _get_state(session: AgentSession, *, source_id: str) -> ToolApprovalState:
    raw_state = session.state.get(source_id)
    if isinstance(raw_state, ToolApprovalState):
        return raw_state
    if isinstance(raw_state, MutableMapping):
        raw_state_mapping = cast(MutableMapping[str, Any], raw_state)
        return ToolApprovalState(
            rules=cast(Sequence[Mapping[str, Any]], raw_state_mapping.get(_RULES_KEY, [])),
            queued_approval_requests=_contents_from_state(raw_state_mapping.get(_QUEUED_APPROVAL_REQUESTS_KEY, [])),
            collected_approval_responses=_contents_from_state(
                raw_state_mapping.get(_COLLECTED_APPROVAL_RESPONSES_KEY, []),
            ),
        )
    if raw_state is not None:
        raise TypeError(f"Session state for {source_id!r} must be a mapping, got {type(raw_state).__name__}.")
    state = ToolApprovalState()
    session.state[source_id] = state.to_dict(exclude={"type"})
    return state


def _save_state(session: AgentSession, state: ToolApprovalState, *, source_id: str) -> None:
    serialized = state.to_dict(exclude={"type"})
    existing = session.state.get(source_id)
    if isinstance(existing, MutableMapping):
        for key, value in cast(MutableMapping[str, Any], existing).items():
            if key not in serialized and key != "type":
                serialized[key] = value
    session.state[source_id] = serialized


def _rule_exists(rules: Sequence[ToolApprovalRule], new_rule: ToolApprovalRule) -> bool:
    for rule in rules:
        if rule.tool_name != new_rule.tool_name:
            continue
        if rule.server_label != new_rule.server_label:
            continue
        if rule.arguments == new_rule.arguments:
            return True
    return False


def _add_rule_if_missing(state: ToolApprovalState, rule: ToolApprovalRule) -> None:
    if not _rule_exists(state.rules, rule):
        state.rules.append(rule)


def _function_call_from_request(request: Content) -> Content | None:
    function_call = request.function_call
    if function_call is None or function_call.type != "function_call" or function_call.name is None:
        return None
    return function_call


def _arguments_match(rule_arguments: Mapping[str, str], function_call: Content) -> bool:
    call_arguments = _serialize_arguments(function_call) or {}
    if len(rule_arguments) != len(call_arguments):
        return False
    return all(call_arguments.get(key) == value for key, value in rule_arguments.items())


def _matches_rule(request: Content, rules: Sequence[ToolApprovalRule]) -> bool:
    function_call = _function_call_from_request(request)
    if function_call is None:
        return False
    for rule in rules:
        if rule.tool_name != function_call.name:
            continue
        if rule.server_label != _server_label(function_call):
            continue
        if rule.arguments is None:
            return True
        if _arguments_match(rule.arguments, function_call):
            return True
    return False


def _get_always_approve_scope(response: Content) -> ToolApprovalScope | None:
    metadata = response.additional_properties.get(ALWAYS_APPROVE_PROPERTY)
    if not isinstance(metadata, Mapping):
        return None
    metadata_mapping = cast(Mapping[str, Any], metadata)
    scope = metadata_mapping.get(ALWAYS_APPROVE_SCOPE_PROPERTY)
    if scope == ALWAYS_APPROVE_TOOL:
        return ALWAYS_APPROVE_TOOL
    if scope == ALWAYS_APPROVE_TOOL_WITH_ARGUMENTS:
        return ALWAYS_APPROVE_TOOL_WITH_ARGUMENTS
    return None


def _clone_without_always_approve_metadata(response: Content) -> Content:
    cloned = copy.deepcopy(response)
    cloned.additional_properties.pop(ALWAYS_APPROVE_PROPERTY, None)
    return cloned


class ToolApprovalMiddleware(AgentMiddleware):
    """Coordinate standing tool approvals and queued approval prompts for an agent.

    This middleware is opt-in and requires callers to run the agent with an
    :class:`AgentSession`, because approval rules and queued requests are stored
    in session state.
    """

    def __init__(
        self,
        *,
        source_id: str = DEFAULT_TOOL_APPROVAL_SOURCE_ID,
        auto_approval_rules: Sequence[ToolApprovalRuleCallback] | None = None,
    ) -> None:
        """Initialize the middleware.

        Keyword Args:
            source_id: Session-state key used by this middleware.
            auto_approval_rules: Optional callbacks that can auto-approve a
                ``function_call``. Each callback receives the function-call
                content and returns ``True`` to approve it.

                .. warning::
                    **Security.** Auto-approval rules may match tool calls by
                    name (each callback receives the full ``function_call``
                    content, including arguments, and can implement stricter,
                    argument-aware matching). A rule provided for one feature
                    (for example a provider's read-only rule) may auto-approve
                    **any** local tool whose name matches, not just the tool the
                    rule was designed for. When adding rules here, ensure no
                    unrelated tools you register collide with a name approved by
                    any rule in this list, otherwise that tool may be
                    auto-approved without a human prompt, bypassing the approval
                    boundary.
        """
        self.source_id = source_id
        self.auto_approval_rules = tuple(auto_approval_rules or ())

    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        """Process one agent invocation."""
        mark_feature_used(FeatureIndex.CORE_TOOL_APPROVAL)
        if context.session is None:
            raise RuntimeError("ToolApprovalMiddleware requires an AgentSession.")

        state = _get_state(context.session, source_id=self.source_id)
        context.client_kwargs.setdefault(_FUNCTION_INVOCATION_BUDGET_STATE_KEY, {})
        context.messages = self._prepare_inbound_messages(context.messages, state)
        await self._drain_auto_approvable_queue(state)
        if next_queued := self._pop_next_queued_request(state):
            _save_state(context.session, state, source_id=self.source_id)
            context.result = self._response_for_queued_request(next_queued, stream=context.stream)
            return
        if context.stream:
            context.result = self._process_stream(context, call_next, state)
            return

        while True:
            context.messages = self._inject_collected_responses(context.messages, state)
            state_changed = bool(state.collected_approval_responses)
            state.collected_approval_responses.clear()
            if state_changed:
                _save_state(context.session, state, source_id=self.source_id)

            await call_next()
            if isinstance(context.result, ResponseStream):
                return
            if context.result is None:
                _save_state(context.session, state, source_id=self.source_id)
                return

            all_auto_approved = await self._process_outbound_messages(context.result.messages, state)
            _save_state(context.session, state, source_id=self.source_id)
            if not all_auto_approved:
                return
            context.messages = []
            context.result = None

    def _response_for_queued_request(
        self,
        request: Content,
        *,
        stream: bool,
    ) -> AgentResponse | ResponseStream[AgentResponseUpdate, AgentResponse]:
        if not stream:
            return AgentResponse(messages=[Message(role="assistant", contents=[request])])

        async def _stream() -> AsyncIterable[AgentResponseUpdate]:
            await sleep(0)
            yield AgentResponseUpdate(role="assistant", contents=[request])

        return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

    def _process_stream(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
        state: ToolApprovalState,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        async def _stream() -> AsyncIterable[AgentResponseUpdate]:
            if context.session is None:
                raise RuntimeError("ToolApprovalMiddleware requires an AgentSession.")
            while True:
                context.messages = self._inject_collected_responses(context.messages, state)
                state_changed = bool(state.collected_approval_responses)
                state.collected_approval_responses.clear()
                if state_changed:
                    _save_state(context.session, state, source_id=self.source_id)

                await call_next()
                if not isinstance(context.result, ResponseStream):
                    raise ValueError("Streaming ToolApprovalMiddleware requires a ResponseStream result.")

                approval_requests: list[Content] = []
                async for update in context.result:
                    approval_contents = [
                        content for content in update.contents if content.type == "function_approval_request"
                    ]
                    if not approval_contents:
                        yield update
                        continue
                    approval_requests.extend(approval_contents)
                    remaining_contents = [
                        content for content in update.contents if content.type != "function_approval_request"
                    ]
                    if remaining_contents:
                        raw_finish_reason = update.finish_reason
                        finish_reason: FinishReasonLiteral | FinishReason | None
                        if isinstance(raw_finish_reason, str):
                            finish_reason = FinishReason(raw_finish_reason)
                        else:
                            finish_reason = cast(FinishReasonLiteral | FinishReason | None, raw_finish_reason)
                        yield AgentResponseUpdate(
                            contents=remaining_contents,
                            role=update.role,
                            author_name=update.author_name,
                            agent_id=update.agent_id,
                            response_id=update.response_id,
                            message_id=update.message_id,
                            created_at=update.created_at,
                            finish_reason=finish_reason,
                            continuation_token=update.continuation_token,
                            additional_properties=update.additional_properties,
                            raw_representation=update.raw_representation,
                        )
                await context.result.get_final_response()
                if not approval_requests:
                    return

                response_messages = [Message(role="assistant", contents=approval_requests)]
                all_auto_approved = await self._process_outbound_messages(response_messages, state)
                _save_state(context.session, state, source_id=self.source_id)
                if not all_auto_approved:
                    for message in response_messages:
                        if message.contents:
                            yield AgentResponseUpdate(role=message.role, contents=message.contents)
                    return
                context.messages = []
                context.result = None

        return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

    def _prepare_inbound_messages(self, messages: Sequence[Message], state: ToolApprovalState) -> list[Message]:
        prepared: list[Message] = []
        for message in messages:
            replacement_contents: list[Content] = []
            changed = False
            for content in message.contents:
                if content.type == "function_approval_response":
                    replacement = self._handle_inbound_approval_response(content, state)
                    state.collected_approval_responses.append(replacement)
                    changed = True
                    continue
                replacement_contents.append(content)

            if not changed:
                prepared.append(message)
                continue
            if replacement_contents:
                cloned = copy.copy(message)
                cloned.contents = replacement_contents
                prepared.append(cloned)
        return prepared

    def _handle_inbound_approval_response(self, response: Content, state: ToolApprovalState) -> Content:
        scope = _get_always_approve_scope(response)
        if scope is None or not response.approved:
            return response

        function_call = response.function_call
        if function_call is not None and function_call.type == "function_call" and function_call.name is not None:
            if scope == ALWAYS_APPROVE_TOOL:
                _add_rule_if_missing(
                    state,
                    ToolApprovalRule(
                        tool_name=function_call.name,
                        server_label=_server_label(function_call),
                    ),
                )
            else:
                _add_rule_if_missing(
                    state,
                    ToolApprovalRule(
                        tool_name=function_call.name,
                        arguments=_serialize_arguments(function_call),
                        server_label=_server_label(function_call),
                    ),
                )
        return _clone_without_always_approve_metadata(response)

    def _inject_collected_responses(self, messages: Sequence[Message], state: ToolApprovalState) -> list[Message]:
        if not state.collected_approval_responses:
            return list(messages)
        return [Message(role="user", contents=list(state.collected_approval_responses)), *messages]

    async def _drain_auto_approvable_queue(self, state: ToolApprovalState) -> None:
        remaining: list[Content] = []
        for request in state.queued_approval_requests:
            if _matches_rule(request, state.rules) or await self._matches_auto_rule(request):
                state.collected_approval_responses.append(request.to_function_approval_response(approved=True))
                continue
            remaining.append(request)
        state.queued_approval_requests = remaining

    def _pop_next_queued_request(self, state: ToolApprovalState) -> Content | None:
        if not state.queued_approval_requests:
            return None
        return state.queued_approval_requests.pop(0)

    async def _process_outbound_messages(self, messages: list[Message], state: ToolApprovalState) -> bool:
        approval_requests = [
            content
            for message in messages
            for content in message.contents
            if content.type == "function_approval_request"
        ]
        if not approval_requests:
            return False

        auto_approved: set[int] = set()
        unresolved: list[Content] = []
        for request in approval_requests:
            if _matches_rule(request, state.rules) or await self._matches_auto_rule(request):
                state.collected_approval_responses.append(request.to_function_approval_response(approved=True))
                auto_approved.add(id(request))
            else:
                unresolved.append(request)

        if not auto_approved and len(unresolved) <= 1:
            return False

        queued_ids: set[int] = set()
        for request in unresolved[1:]:
            queued_ids.add(id(request))
            state.queued_approval_requests.append(request)

        remove_ids = auto_approved | queued_ids
        self._remove_approval_requests(messages, remove_ids)
        return not unresolved

    @staticmethod
    def _remove_approval_requests(messages: list[Message], remove_ids: set[int]) -> None:
        for message_index in range(len(messages) - 1, -1, -1):
            message = messages[message_index]
            filtered = [
                content
                for content in message.contents
                if content.type != "function_approval_request" or id(content) not in remove_ids
            ]
            if len(filtered) == len(message.contents):
                continue
            if filtered:
                message.contents = filtered
            else:
                messages.pop(message_index)

    async def _matches_auto_rule(self, request: Content) -> bool:
        function_call = _function_call_from_request(request)
        if function_call is None:
            return False
        for rule in self.auto_approval_rules:
            result = rule(function_call)
            if inspect.isawaitable(result):
                result = await result
            if result:
                return True
        return False


__all__ = [
    "ALWAYS_APPROVE_PROPERTY",
    "ALWAYS_APPROVE_SCOPE_PROPERTY",
    "ALWAYS_APPROVE_TOOL",
    "ALWAYS_APPROVE_TOOL_WITH_ARGUMENTS",
    "DEFAULT_TOOL_APPROVAL_SOURCE_ID",
    "ToolApprovalMiddleware",
    "ToolApprovalRule",
    "ToolApprovalRuleCallback",
    "ToolApprovalState",
    "create_always_approve_tool_response",
    "create_always_approve_tool_with_arguments_response",
]
