# Copyright (c) Microsoft. All rights reserved.

"""Deterministic ATR validation middleware for Microsoft Agent Framework.

Two middleware are provided:

* :class:`ATRFunctionMiddleware` enforces at the tool-execution boundary. It
  inspects validated tool arguments and blocks the call BEFORE it runs when the
  arguments match an ATR rule (the pattern recommended in issue #5366).
* :class:`ATRAgentMiddleware` scans inbound user messages before the agent
  invokes the model and blocks the run on a match.

Detection is delegated to the local ATR engine (see :mod:`._engine`); there is
no model call in the enforcement path, so decisions are reproducible.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agent_framework import (
    AgentContext,
    AgentMiddleware,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareTermination,
)
from pydantic import BaseModel

from ._engine import ATRDetector

logger = logging.getLogger("agent_framework.atr")


def _arguments_to_text(arguments: BaseModel | Mapping[str, Any]) -> str:
    """Flatten tool arguments into a single string for scanning.

    Args:
        arguments: The validated tool arguments, either a pydantic model or a
            plain mapping.

    Returns:
        The argument values joined into a single space-separated string.
    """
    values = arguments.model_dump() if isinstance(arguments, BaseModel) else arguments
    return " ".join(str(value) for value in values.values())


class ATRFunctionMiddleware(FunctionMiddleware):
    """Blocks tool calls whose validated arguments match an ATR rule.

    The check is deterministic and runs BEFORE ``call_next()``, so a matched
    tool never executes. On a match the detection is recorded on
    ``context.metadata['atr_detection']`` for auditability.

    Args:
        detector: A shared :class:`ATRDetector`. When ``None`` a detector is
            created with the bundled ruleset.
        audit_only: When ``True`` the tool is allowed to run and the match is
            only recorded and logged (dry-run / shadow mode).
        min_severity: Minimum severity to act on when constructing a default
            detector. Ignored when ``detector`` is provided.

    Examples:
        .. code-block:: python

            from agent_framework import Agent
            from agent_framework_atr import ATRFunctionMiddleware

            agent = Agent(client=client, instructions="...", middleware=[ATRFunctionMiddleware()])
    """

    def __init__(
        self,
        *,
        detector: ATRDetector | None = None,
        audit_only: bool = False,
        min_severity: str = "informational",
    ) -> None:
        self._detector = detector or ATRDetector(min_severity=min_severity)
        self._audit_only = audit_only

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Validate tool arguments and block, or allow, the tool call."""
        text = _arguments_to_text(context.arguments)
        match = self._detector.detect(text, event_type="tool_call", field="tool_args")
        if match is not None:
            context.metadata["atr_detection"] = match
            if self._audit_only:
                logger.warning(
                    "[ATR] tool '%s' matched rule %s (%s) -- audit only, allowing.",
                    context.function.name,
                    match.rule_id,
                    match.severity,
                )
                await call_next()
                return
            logger.warning(
                "[ATR] blocked tool '%s': arguments matched rule %s (%s).",
                context.function.name,
                match.rule_id,
                match.severity,
            )
            raise MiddlewareTermination(
                f"ATR validation blocked tool '{context.function.name}' "
                f"(rule: {match.rule_id}, severity: {match.severity})"
            )
        await call_next()


class ATRAgentMiddleware(AgentMiddleware):
    """Scans inbound user messages and blocks the run on an ATR match.

    Runs before the agent invokes the model, evaluating the concatenated user
    message text as an ``llm_input`` event. On a match the detection is recorded
    on ``context.metadata['atr_detection']``.

    Args:
        detector: A shared :class:`ATRDetector`. When ``None`` a detector is
            created with the bundled ruleset.
        audit_only: When ``True`` the run is allowed to proceed and the match is
            only recorded and logged (dry-run / shadow mode).
        min_severity: Minimum severity to act on when constructing a default
            detector. Ignored when ``detector`` is provided.

    Examples:
        .. code-block:: python

            from agent_framework import Agent
            from agent_framework_atr import ATRAgentMiddleware

            agent = Agent(client=client, instructions="...", middleware=[ATRAgentMiddleware()])
    """

    def __init__(
        self,
        *,
        detector: ATRDetector | None = None,
        audit_only: bool = False,
        min_severity: str = "informational",
    ) -> None:
        self._detector = detector or ATRDetector(min_severity=min_severity)
        self._audit_only = audit_only

    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Scan inbound user messages and block, or allow, the agent run."""
        text = " ".join(message.text for message in context.messages if message.role == "user" and message.text)
        match = self._detector.detect(text, event_type="llm_input", field="user_input")
        if match is not None:
            context.metadata["atr_detection"] = match
            if not self._audit_only:
                logger.warning(
                    "[ATR] blocked agent input: matched rule %s (%s).",
                    match.rule_id,
                    match.severity,
                )
                raise MiddlewareTermination(
                    f"ATR validation blocked agent input (rule: {match.rule_id}, severity: {match.severity})"
                )
            logger.warning(
                "[ATR] agent input matched rule %s (%s) -- audit only, allowing.",
                match.rule_id,
                match.severity,
            )
        await call_next()
