# Copyright (c) Microsoft. All rights reserved.

"""Cua integration middleware for Agent Framework."""

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import (
    ChatMessage,
    ChatMiddleware,
    ChatResponse,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
)
from agent_framework._middleware import ChatContext

try:
    from agent import ComputerAgent  # type: ignore
    from computer import Computer  # type: ignore

    CUA_AVAILABLE = True
except ImportError:
    CUA_AVAILABLE = False
    ComputerAgent = Any  # type: ignore
    Computer = Any  # type: ignore

from ._types import CuaModelId, CuaResult, CuaStep

# Import CuaChatClient for type checking
try:
    from ._chat_client import CuaChatClient
except ImportError:
    CuaChatClient = None  # type: ignore


class CuaAgentMiddleware(ChatMiddleware):
    """Middleware that delegates to Cua's ComputerAgent for model execution.

    This provides Agent Framework access to 100+ model configurations
    (OpenCUA, InternVL, UI-Tars, GLM, etc.) and composite agents,
    while maintaining Agent Framework's orchestration and human-in-the-loop.

    Architecture:
        Agent Framework → CuaAgentMiddleware → Cua ComputerAgent
                                                ↓
                                            Model + Computer Loop
                                                ↓
                                            Results
                                                ↓
        Agent Framework ← CuaAgentMiddleware ← Cua ComputerAgent

    Examples:
        .. code-block:: python

            from agent_framework import ChatAgent
            from agent_framework.cua import CuaChatClient, CuaAgentMiddleware
            from computer import Computer

            async with Computer(os_type="linux", provider_type="docker") as computer:
                chat_client = CuaChatClient(
                    model="anthropic/claude-sonnet-4-5-20250929",
                    instructions="You are a desktop automation assistant.",
                )

                middleware = CuaAgentMiddleware(computer=computer)

                agent = ChatAgent(
                    chat_client=chat_client,
                    middleware=[middleware],
                )

                response = await agent.run("Open Firefox and search for Python")
    """

    def __init__(
        self,
        computer: "Computer",
        *,
        model: CuaModelId | None = None,
        instructions: str | None = None,
        max_trajectory_budget: float = 5.0,
        require_approval: bool = True,
        approval_interval: int = 5,
    ) -> None:
        """Initialize CuaAgentMiddleware.

        Args:
            computer: Cua Computer instance for desktop automation
            model: Model identifier (supports 100+ configs). If not provided,
                will be extracted from CuaChatClient. Options:
                - "anthropic/claude-sonnet-4-5-20250929"
                - "openai/gpt-4o"
                - "huggingface-local/ByteDance/OpenCUA-7B"
                - "huggingface-local/OpenGVLab/InternVL2-8B"
                - Composite: "ui-model+planning-model"
            instructions: Optional system instructions for the agent.
                If not provided, will be extracted from CuaChatClient.
            max_trajectory_budget: Max cost budget for Cua agent loop
            require_approval: Whether to require human approval
            approval_interval: Steps between approval requests

        Note:
            Model and instructions can be provided either:
            1. Via CuaChatClient (recommended): Pass to chat_client parameter
            2. Directly to middleware: Pass to this __init__ method
            If both are provided, middleware parameters take precedence.
        """
        if not CUA_AVAILABLE:
            raise ImportError("Cua packages not installed. Install with: pip install agent-framework-cua")

        self.computer = computer
        self.model = model
        self.instructions = instructions
        self.max_trajectory_budget = max_trajectory_budget
        self.require_approval = require_approval
        self.approval_interval = approval_interval

        # Will be initialized in first process() call when chat_client is available
        self.cua_agent: ComputerAgent | None = None

        self._step_count = 0
        self._trajectory: list[CuaStep] = []

    async def process(
        self,
        context: ChatContext,
        next: Callable[[ChatContext], Awaitable[None]],
    ) -> None:
        """Process chat by delegating to Cua's ComputerAgent.

        Flow:
        1. Extract model/instructions from CuaChatClient if needed
        2. Initialize Cua agent on first call
        3. Extract messages from Agent Framework context
        4. Check if approval needed (if steps >= approval_interval)
        5. If approved, call Cua agent with messages
        6. Cua handles entire model + computer execution loop
        7. Transform Cua results back to Agent Framework format
        8. Set context.result with ChatResponse

        Args:
            context: Chat context containing messages and options
            next: Function to call next middleware (not used; execution is handled by Cua)
        """
        # Initialize Cua agent on first call
        if self.cua_agent is None:
            model = self.model
            instructions = self.instructions

            # Extract from CuaChatClient if not explicitly provided
            if CuaChatClient is not None and hasattr(context, "chat_client"):
                chat_client = context.chat_client
                if isinstance(chat_client, CuaChatClient):
                    # Use client values if middleware values not provided
                    if model is None:
                        model = chat_client.model
                    if instructions is None:
                        instructions = chat_client.instructions

            # Default model if still not provided
            if model is None:
                model = "anthropic/claude-sonnet-4-5-20250929"

            # Create Cua ComputerAgent
            self.cua_agent = ComputerAgent(
                model=model,
                tools=[self.computer],
                instructions=instructions,
                max_trajectory_budget=self.max_trajectory_budget,
            )

        # Check if approval is required before proceeding
        if self.require_approval and self._should_request_approval():
            approved = await self._request_approval(context, next)
            if not approved:
                context.result = self._create_stopped_response("Computer use was not approved by user")
                context.terminate = True
                return

        # Extract messages from context
        messages = self._extract_messages(context)

        # Delegate to Cua's ComputerAgent
        # Cua handles: model call → parse response → execute computer actions → loop
        try:
            cua_result = await self._run_cua_complete(messages)

            # Update trajectory and step count
            self._step_count += len(cua_result.get("steps", []))
            self._trajectory.extend(cua_result.get("steps", []))

            # Transform to Agent Framework format and set result
            context.result = self._transform_to_agent_framework(cua_result)

        except Exception as e:
            context.result = self._create_error_response(str(e))

        # Terminate execution since Cua handles the complete agent loop
        context.terminate = True

    def _extract_messages(self, context: ChatContext) -> list[dict[str, Any]]:
        """Extract messages from Agent Framework context to Cua format."""
        messages = []

        for msg in context.messages:
            # Convert Agent Framework ChatMessage to Cua format
            cua_msg: dict[str, Any] = {
                "role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
            }

            # Handle different content types - use msg.text or msg.contents
            if hasattr(msg, "text") and msg.text:
                cua_msg["content"] = msg.text
            elif hasattr(msg, "contents") and msg.contents:
                if len(msg.contents) == 1 and hasattr(msg.contents[0], "text"):
                    cua_msg["content"] = msg.contents[0].text
                else:
                    cua_msg["content"] = [self._convert_content_block(block) for block in msg.contents]
            else:
                cua_msg["content"] = ""

            messages.append(cua_msg)

        return messages

    async def _run_cua_complete(self, messages: list[dict[str, Any]]) -> CuaResult:
        """Run Cua agent to completion.

        Cua's agent.run() handles:
        - Model inference
        - Response parsing (provider-agnostic)
        - Computer action execution
        - Multi-step loops until task complete
        """
        results: list[dict[str, Any]] = []

        async for result in self.cua_agent.run(messages):
            results.append(result)

        # Return final result
        return results[-1] if results else {}

    def _should_request_approval(self) -> bool:
        """Check if we should request approval before continuing."""
        return self.require_approval and self._step_count > 0 and self._step_count % self.approval_interval == 0

    async def _request_approval(
        self,
        context: ChatContext,
        next: Callable[[ChatContext], Awaitable[None]],
    ) -> bool:
        """Request human approval to continue computer use.

        Uses Agent Framework's FunctionApprovalRequestContent pattern.
        """
        # Create approval request
        approval_msg = ChatMessage(
            role="assistant",
            content=FunctionApprovalRequestContent(
                function_name="computer_use_continuation",
                arguments={
                    "steps_completed": self._step_count,
                    "trajectory": self._get_trajectory_summary(),
                },
                description=(f"Computer use has completed {self._step_count} steps. Approve to continue?"),
            ),
        )

        # Add to context and get user response
        context.messages.append(approval_msg)
        await next(context)

        # Parse approval response from context.result
        if context.result and isinstance(context.result, ChatResponse):
            for msg in context.result.messages:
                for content in msg.contents:
                    if isinstance(content, FunctionApprovalResponseContent):
                        return content.approved

        # Default: don't proceed without explicit approval
        return False

    def _transform_to_agent_framework(self, cua_result: CuaResult) -> ChatResponse:
        """Transform Cua agent result to Agent Framework ChatResponse.

        Cua result format:
        {
            'output': [
                {'type': 'message', 'content': [{'text': '...'}]},
                {'type': 'screenshot', 'data': b'...'},
            ],
            'steps': [...],
            'usage': {'total_tokens': 1234, 'cost': 0.05},
        }
        """
        messages: list[ChatMessage] = []

        # Extract output from Cua result
        for item in cua_result.get("output", []):
            if item.get("type") == "message":
                # Text message from model
                content = item.get("content", [])
                if isinstance(content, list) and len(content) > 0:
                    text = content[0].get("text", "") if isinstance(content[0], dict) else str(content[0])
                else:
                    text = str(content)

                messages.append(
                    ChatMessage(
                        role="assistant",
                        text=text,
                    )
                )

            elif item.get("type") == "error":
                # Error during execution
                messages.append(
                    ChatMessage(
                        role="tool",
                        text=f"Error: {item.get('message', 'Unknown error')}",
                    )
                )

        # If no messages, add a default response
        if not messages:
            messages.append(ChatMessage(role="assistant", text="Task completed."))

        # Create response
        return ChatResponse(
            messages=messages,
            usage_details=cua_result.get("usage"),
            additional_properties={
                "cua_steps": len(cua_result.get("steps", [])),
                "cua_model": self.model,
            },
        )

    def _get_trajectory_summary(self) -> list[dict[str, Any]]:
        """Get summary of execution trajectory for approval."""
        return [
            {
                "step": i,
                "action": step.get("action", "unknown"),
                "result": step.get("result", "unknown"),
            }
            for i, step in enumerate(self._trajectory[-5:])  # Last 5 steps
        ]

    def _convert_content_block(self, block: Any) -> dict[str, Any]:
        """Convert Agent Framework content block to Cua format."""
        if isinstance(block, dict):
            # Handle different content types
            if block.get("type") == "text":
                return {"type": "text", "text": block.get("text", "")}
            if block.get("type") == "image":
                return {"type": "image", "source": block.get("source")}
            return block
        # If the block is an object with attributes
        if hasattr(block, "text"):
            return {"type": "text", "text": block.text}
        return {"type": "text", "text": str(block)}

    def _create_stopped_response(self, reason: str) -> ChatResponse:
        """Create response when execution is stopped."""
        return ChatResponse(
            messages=[
                ChatMessage(
                    role="assistant",
                    text=f"Computer use stopped: {reason}",
                )
            ],
            additional_properties={"stopped": True, "reason": reason},
        )

    def _create_error_response(self, error: str) -> ChatResponse:
        """Create error response."""
        return ChatResponse(
            messages=[
                ChatMessage(
                    role="assistant",
                    text=f"Error during computer use: {error}",
                )
            ],
            additional_properties={"error": True, "message": error},
        )
