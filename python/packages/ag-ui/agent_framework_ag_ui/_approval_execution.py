# Copyright (c) Microsoft. All rights reserved.

"""Track AG-UI approval execution through the agent's normal middleware interfaces."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agent_framework import (
    AgentSession,
    ChatContext,
    ChatMiddleware,
    Content,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareFailure,
)
from agent_framework._tools import (
    _APPROVAL_REQUEST_ID_KEY,
    _TOOL_APPROVAL_STATE_KEY,
    _load_pending_approval_requests,
    _save_pending_approval_requests,
    normalize_function_invocation_configuration,
)
from agent_framework.exceptions import UserInputRequiredException

from ._approval_lifecycle import (
    ApprovalExecutionOwner,
    ApprovalLifecycle,
    ApprovalOutcome,
    ApprovalStatus,
    AuthorizedExecution,
    ForwardedPendingToolTransitionOwner,
)

COLLECTED_APPROVAL_OCCURRENCE_KEY = "_agui_collected_approval_occurrence"


class ApprovalInvocationDisabledError(Exception):
    """The current invocation configuration prevents an unstarted local approval."""


class InRunPendingToolTransitionOwner(ForwardedPendingToolTransitionOwner):
    """Observe core-owned execution without starting it while preparing transport messages."""

    async def forward(self, intent: AuthorizedExecution, *, lifecycle: ApprovalLifecycle) -> list[Content]:
        return await self._forwarder()

    def record_outcome(
        self, intent: AuthorizedExecution, results: list[Content], *, lifecycle: ApprovalLifecycle
    ) -> ApprovalOutcome:
        if lifecycle.get(intent.identity).status is ApprovalStatus.CLAIMED:
            lifecycle.begin_execution(intent, owner=intent.owner)
        if intent.owner is ApprovalExecutionOwner.LOCAL:
            return lifecycle.settle(intent, results)
        return super().record_outcome(intent, results, lifecycle=lifecycle)

    def record_reapproval(self, intent: AuthorizedExecution, request: Content, *, lifecycle: ApprovalLifecycle) -> None:
        if lifecycle.get(intent.identity).status is ApprovalStatus.CLAIMED:
            lifecycle.begin_execution(intent, owner=intent.owner)
        super().record_reapproval(intent, request, lifecycle=lifecycle)


class InRunApprovalExecution:
    """Bind validated transport approvals to existing function and chat middleware seams."""

    def __init__(self, lifecycle: ApprovalLifecycle, session: AgentSession, client: Any) -> None:
        self.lifecycle = lifecycle
        self.session = session
        self.client = client
        self._local: dict[str, AuthorizedExecution] = {}
        self._hosted: dict[str, AuthorizedExecution] = {}
        self.function_middleware = _ApprovalFunctionMiddleware(self)
        self.chat_middleware = _ApprovalChatMiddleware(self)

    def register(self, intent: AuthorizedExecution, response: Content) -> None:
        occurrence = self.lifecycle.get(intent.identity)
        if intent.owner is ApprovalExecutionOwner.HOSTED:
            if response.id is None:
                raise ValueError("A hosted approval must carry its authoritative request id.")
            self._hosted[response.id] = intent
            return
        if response.function_call is None:
            raise ValueError("A local approval must carry its authoritative function call.")
        if response.approved is True:
            self._local[occurrence.function_call_id] = intent
        request_id = occurrence.response_id or occurrence.function_call_id
        pending = _load_pending_approval_requests(self.session)
        previous = pending.get(request_id)
        properties = dict(previous.additional_properties) if previous is not None else {}
        if request_id != occurrence.function_call_id:
            properties["_replacement_approval_request"] = True
        pending[request_id] = Content.from_function_approval_request(
            id=request_id,
            function_call=Content.from_dict(response.function_call.to_dict()),
            additional_properties=properties,
        )
        _save_pending_approval_requests(self.session, pending)
        response.id = request_id
        response.additional_properties[_APPROVAL_REQUEST_ID_KEY] = request_id

    def ensure_enabled(self) -> None:
        if not any(
            self.lifecycle.get(intent.identity).status is ApprovalStatus.CLAIMED for intent in self._local.values()
        ):
            return
        config = normalize_function_invocation_configuration(
            getattr(self.client, "function_invocation_configuration", None)
        )
        if not config.get("enabled", True):
            raise ApprovalInvocationDisabledError("Function invocation is disabled.")

    def begin_function(self, context: FunctionInvocationContext) -> AuthorizedExecution | None:
        response = context.metadata.get("approval_response")
        if not isinstance(response, Content) or response.approved is not True:
            return None
        occurrence_id = context.metadata.get("function_call_occurrence_id")
        intent = self._local.get(occurrence_id) if isinstance(occurrence_id, str) else None
        if intent is None:
            return None
        if context.session is not self.session:
            raise MiddlewareFailure("Approval execution belongs to a different session.")
        self.ensure_enabled()
        self.lifecycle.begin_execution(intent, owner=intent.owner)
        return intent

    def begin_hosted(self, context: ChatContext) -> None:
        self.ensure_enabled()
        for message in context.messages:
            for content in message.contents:
                if content.type != "function_approval_response" or content.approved is not True:
                    continue
                intent = self._hosted.get(content.id) if content.id is not None else None
                if intent is not None and self.lifecycle.get(intent.identity).status is ApprovalStatus.CLAIMED:
                    self.lifecycle.begin_execution(intent, owner=intent.owner)

    def retain_collected_decisions(self) -> None:
        """Preserve grants retained by the wrapped Agent's approval middleware."""
        state = self.session.state.get(_TOOL_APPROVAL_STATE_KEY)
        if not isinstance(state, Mapping):
            return
        responses = state.get("collected_approval_responses", [])
        updated_responses = list(responses)
        for index, value in enumerate(responses):
            response = value if isinstance(value, Content) else Content.from_dict(value)
            if response.approved is not True or response.function_call is None:
                continue
            occurrence_id = response.function_call.id
            intent = self._local.get(occurrence_id) if occurrence_id is not None else None
            if intent is None and response.id is not None:
                intent = self._hosted.get(response.id)
            if intent is None:
                continue
            occurrence = self.lifecycle.get(intent.identity)
            request_id = response.additional_properties.get(_APPROVAL_REQUEST_ID_KEY) or response.id
            if occurrence.status is ApprovalStatus.CLAIMED and request_id == (
                occurrence.response_id or occurrence.function_call_id
            ):
                self.lifecycle.retain_collected_decision(intent)
                response.additional_properties[COLLECTED_APPROVAL_OCCURRENCE_KEY] = intent.identity.occurrence_id
                updated_responses[index] = response.to_dict()
        self.session.state[_TOOL_APPROVAL_STATE_KEY] = {
            **state,
            "collected_approval_responses": updated_responses,
        }


class _ApprovalFunctionMiddleware(FunctionMiddleware):
    def __init__(self, execution: InRunApprovalExecution) -> None:
        self._execution = execution

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        intent = self._execution.begin_function(context)
        try:
            await call_next()
        except UserInputRequiredException as exc:
            if intent is not None and not any(content.type == "function_result" for content in exc.contents):
                self._execution.lifecycle.defer(intent, list(exc.contents), owner=intent.owner)
            raise


class _ApprovalChatMiddleware(ChatMiddleware):
    def __init__(self, execution: InRunApprovalExecution) -> None:
        self._execution = execution

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        self._execution.begin_hosted(context)
        await call_next()
