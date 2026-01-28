# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

from agent_framework import FunctionInvocationContext, tool, function_middleware
from agent_framework.openai import OpenAIChatClient
from pydantic import Field

"""
Runtime Context Delegation Patterns

This sample demonstrates different patterns for passing runtime context (API tokens,
session data, etc.) to tools and sub-agents.

Patterns Demonstrated:

1. **Pattern 1: Single Agent with Middleware & Closure** (Lines 130-180)
   - Best for: Single agent with multiple tools
   - How: Middleware stores kwargs in container, tools access via closure
   - Pros: Simple, explicit state management
   - Cons: Requires container instance per agent

2. **Pattern 2: Hierarchical Agents with kwargs Propagation** (Lines 190-240)
   - Best for: Parent-child agent delegation with as_tool()
   - How: kwargs automatically propagate through as_tool() wrapper
   - Pros: Automatic, works with nested delegation, clean separation
   - Cons: None - this is the recommended pattern for hierarchical agents

3. **Pattern 3: Mixed - Hierarchical with Middleware** (Lines 250-300)
   - Best for: Complex scenarios needing both delegation and state management
   - How: Combines automatic kwargs propagation with middleware processing
   - Pros: Maximum flexibility, can transform/validate context at each level
   - Cons: More complex setup

Key Concepts:
- Runtime Context: Session-specific data like API tokens, user IDs, tenant info
- Middleware: Intercepts function calls to access/modify kwargs
- Closure: Functions capturing variables from outer scope
- kwargs Propagation: Automatic forwarding of runtime context through delegation chains
"""


class SessionContextContainer:
    """Container for runtime session context accessible via closure."""

    def __init__(self) -> None:
        """Initialize with None values for runtime context."""
        self.api_token: str | None = None
        self.user_id: str | None = None
        self.session_metadata: dict[str, str] = {}

    async def inject_context_middleware(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Middleware that extracts runtime context from kwargs and stores in container.

        This middleware runs before tool execution and makes runtime context
        available to tools via the container instance.
        """
        # Extract runtime context from kwargs
        self.api_token = context.kwargs.get("api_token")
        self.user_id = context.kwargs.get("user_id")
        self.session_metadata = context.kwargs.get("session_metadata", {})

        # Log what we captured (for demonstration)
        if self.api_token or self.user_id:
            print("[Middleware] Captured runtime context:")
            print(f"  - API Token: {'[PRESENT]' if self.api_token else '[NOT PROVIDED]'}")
            print(f"  - User ID: {'[PRESENT]' if self.user_id else '[NOT PROVIDED]'}")
            print(f"  - Session Metadata Keys: {list(self.session_metadata.keys())}")

        # Continue to tool execution
        await next(context)


# Create a container instance that will be shared via closure
runtime_context = SessionContextContainer()


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
async def send_email(
    to: Annotated[str, Field(description="Recipient email address")],
    subject: Annotated[str, Field(description="Email subject line")],
    body: Annotated[str, Field(description="Email body content")],
) -> str:
    """Send an email using authenticated API (simulated).

    This function accesses runtime context (API token, user ID) via closure
    from the runtime_context container.
    """
    # Access runtime context via closure
    token = runtime_context.api_token
    user_id = runtime_context.user_id
    tenant = runtime_context.session_metadata.get("tenant", "unknown")

    print("\n[send_email] Executing with runtime context:")
    print(f"  - Token: {'[PRESENT]' if token else '[NOT PROVIDED]'}")
    print(f"  - User ID: {'[PRESENT]' if user_id else '[NOT PROVIDED]'}")
    print(f"  - Tenant: {'[PRESENT]' if tenant and tenant != 'unknown' else '[NOT PROVIDED]'}")
    print("  - Recipient count: 1")
    print(f"  - Subject length: {len(subject)} chars")

    # Simulate API call with authentication
    if not token:
        return "ERROR: No API token provided - cannot send email"

    # Simulate sending email
    return f"Email sent to {to} from user {user_id} (tenant: {tenant}). Subject: '{subject}'"


@tool(approval_mode="never_require")
async def send_notification(
    message: Annotated[str, Field(description="Notification message to send")],
    priority: Annotated[str, Field(description="Priority level: low, medium, high")] = "medium",
) -> str:
    """Send a push notification using authenticated API (simulated).

    This function accesses runtime context via closure from runtime_context.
    """
    token = runtime_context.api_token
    user_id = runtime_context.user_id

    print("\n[send_notification] Executing with runtime context:")
    print(f"  - Token: {'[PRESENT]' if token else '[NOT PROVIDED]'}")
    print(f"  - User ID: {'[PRESENT]' if user_id else '[NOT PROVIDED]'}")
    print(f"  - Message length: {len(message)} chars")
    print(f"  - Priority: {priority}")

    if not token:
        return "ERROR: No API token provided - cannot send notification"

    return f"Notification sent to user {user_id} with priority {priority}: {message}"


async def pattern_1_single_agent_with_closure() -> None:
    """Pattern 1: Single agent with middleware and closure for runtime context."""
    print("\n" + "=" * 70)
    print("PATTERN 1: Single Agent with Middleware & Closure")
    print("=" * 70)
    print("Use case: Single agent with multiple tools sharing runtime context")
    print()

    client = OpenAIChatClient(model_id="gpt-4o-mini")

    # Create agent with both tools and shared context via middleware
    communication_agent = client.as_agent(
        name="communication_agent",
        instructions=(
            "You are a communication assistant that can send emails and notifications. "
            "Use send_email for email tasks and send_notification for notification tasks."
        ),
        tools=[send_email, send_notification],
        # Both tools share the same context container via middleware
        middleware=[runtime_context.inject_context_middleware],
    )

    # Test 1: Send email with runtime context
    print("\n" + "=" * 70)
    print("TEST 1: Email with Runtime Context")
    print("=" * 70)

    user_query = (
        "Send an email to john@example.com with subject 'Meeting Tomorrow' and body 'Don't forget our 2pm meeting.'"
    )
    print(f"\nUser: {user_query}")

    result1 = await communication_agent.run(
        user_query,
        # Runtime context passed as kwargs
        api_token="sk-test-token-xyz-789",
        user_id="user-12345",
        session_metadata={"tenant": "acme-corp", "region": "us-west"},
    )

    print(f"\nAgent: {result1.text}")

    # Test 2: Send notification with different runtime context
    print("\n" + "=" * 70)
    print("TEST 2: Notification with Different Runtime Context")
    print("=" * 70)

    user_query2 = "Send a high priority notification saying 'Your order has shipped!'"
    print(f"\nUser: {user_query2}")

    result2 = await communication_agent.run(
        user_query2,
        # Different runtime context for this request
        api_token="sk-prod-token-abc-456",
        user_id="user-67890",
        session_metadata={"tenant": "store-inc", "region": "eu-central"},
    )

    print(f"\nAgent: {result2.text}")

    # Test 3: Both email and notification in one request
    print("\n" + "=" * 70)
    print("TEST 3: Multiple Tools in One Request")
    print("=" * 70)

    user_query3 = (
        "Send an email to alice@example.com about the new feature launch "
        "and also send a notification to remind about the team meeting."
    )
    print(f"\nUser: {user_query3}")

    result3 = await communication_agent.run(
        user_query3,
        api_token="sk-dev-token-def-123",
        user_id="user-11111",
        session_metadata={"tenant": "dev-team", "region": "us-east"},
    )

    print(f"\nAgent: {result3.text}")

    # Test 4: Missing context - show error handling
    print("\n" + "=" * 70)
    print("TEST 4: Missing Runtime Context (Error Case)")
    print("=" * 70)

    user_query4 = "Send an email to test@example.com with subject 'Test'"
    print(f"\nUser: {user_query4}")
    print("Note: Running WITHOUT api_token to demonstrate error handling")

    result4 = await communication_agent.run(
        user_query4,
        # Missing api_token - tools should handle gracefully
        user_id="user-22222",
    )

    print(f"\nAgent: {result4.text}")

    print("\n✓ Pattern 1 complete - Middleware & closure pattern works for single agents")


# Pattern 2: Hierarchical agents with automatic kwargs propagation
# ================================================================


# Create tools for sub-agents (these will use kwargs propagation)
@tool(approval_mode="never_require")
async def send_email_v2(
    to: Annotated[str, Field(description="Recipient email")],
    subject: Annotated[str, Field(description="Subject")],
    body: Annotated[str, Field(description="Body")],
) -> str:
    """Send email - demonstrates kwargs propagation pattern."""
    # In this pattern, we can create a middleware to access kwargs
    # But for simplicity, we'll just simulate the operation
    return f"Email sent to {to} with subject '{subject}'"


@tool(approval_mode="never_require")
async def send_sms(
    phone: Annotated[str, Field(description="Phone number")],
    message: Annotated[str, Field(description="SMS message")],
) -> str:
    """Send SMS message."""
    return f"SMS sent to {phone}: {message}"


async def pattern_2_hierarchical_with_kwargs_propagation() -> None:
    """Pattern 2: Hierarchical agents with automatic kwargs propagation through as_tool()."""
    print("\n" + "=" * 70)
    print("PATTERN 2: Hierarchical Agents with kwargs Propagation")
    print("=" * 70)
    print("Use case: Parent agent delegates to specialized sub-agents")
    print("Feature: Runtime kwargs automatically propagate through as_tool()")
    print()

    # Track kwargs at each level
    email_agent_kwargs: dict[str, object] = {}
    sms_agent_kwargs: dict[str, object] = {}

    @function_middleware
    async def email_kwargs_tracker(
        context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
    ) -> None:
        email_agent_kwargs.update(context.kwargs)
        print(f"[EmailAgent] Received runtime context: {list(context.kwargs.keys())}")
        await next(context)

    @function_middleware
    async def sms_kwargs_tracker(
        context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
    ) -> None:
        sms_agent_kwargs.update(context.kwargs)
        print(f"[SMSAgent] Received runtime context: {list(context.kwargs.keys())}")
        await next(context)

    client = OpenAIChatClient(model_id="gpt-4o-mini")

    # Create specialized sub-agents
    email_agent = client.as_agent(
        name="email_agent",
        instructions="You send emails using the send_email_v2 tool.",
        tools=[send_email_v2],
        middleware=[email_kwargs_tracker],
    )

    sms_agent = client.as_agent(
        name="sms_agent",
        instructions="You send SMS messages using the send_sms tool.",
        tools=[send_sms],
        middleware=[sms_kwargs_tracker],
    )

    # Create coordinator that delegates to sub-agents
    coordinator = client.as_agent(
        name="coordinator",
        instructions=(
            "You coordinate communication tasks. "
            "Use email_sender for emails and sms_sender for SMS. "
            "Delegate to the appropriate specialized agent."
        ),
        tools=[
            email_agent.as_tool(
                name="email_sender",
                description="Send emails to recipients",
                arg_name="task",
            ),
            sms_agent.as_tool(
                name="sms_sender",
                description="Send SMS messages",
                arg_name="task",
            ),
        ],
    )

    # Test: Runtime context propagates automatically
    print("Test: Send email with runtime context\n")
    await coordinator.run(
        "Send an email to john@example.com with subject 'Meeting' and body 'See you at 2pm'",
        api_token="secret-token-abc",
        user_id="user-999",
        tenant_id="tenant-acme",
    )

    print(f"\n[Verification] EmailAgent received kwargs keys: {list(email_agent_kwargs.keys())}")
    print(f"  - api_token: {'[PRESENT]' if email_agent_kwargs.get('api_token') else '[NOT PROVIDED]'}")
    print(f"  - user_id: {'[PRESENT]' if email_agent_kwargs.get('user_id') else '[NOT PROVIDED]'}")
    print(f"  - tenant_id: {'[PRESENT]' if email_agent_kwargs.get('tenant_id') else '[NOT PROVIDED]'}")

    print("\n✓ Pattern 2 complete - kwargs automatically propagate through as_tool()")


# Pattern 3: Mixed pattern - hierarchical with middleware processing
# ===================================================================


class AuthContextMiddleware:
    """Middleware that validates and transforms runtime context."""

    def __init__(self) -> None:
        self.validated_tokens: list[str] = []

    async def validate_and_track(
        self, context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
    ) -> None:
        """Validate API token and track usage."""
        api_token = context.kwargs.get("api_token")

        if api_token:
            # Simulate token validation
            if api_token.startswith("valid-"):
                print("[AuthMiddleware] Token validated successfully")
                self.validated_tokens.append(api_token)
            else:
                print("[AuthMiddleware] Token validation failed")
                # Could set context.terminate = True to block execution
        else:
            print("[AuthMiddleware] No API token provided")

        await next(context)


@tool(approval_mode="never_require")
async def protected_operation(operation: Annotated[str, Field(description="Operation to perform")]) -> str:
    """Protected operation that requires authentication."""
    return f"Executed protected operation: {operation}"


async def pattern_3_hierarchical_with_middleware() -> None:
    """Pattern 3: Hierarchical agents with middleware processing at each level."""
    print("\n" + "=" * 70)
    print("PATTERN 3: Hierarchical with Middleware Processing")
    print("=" * 70)
    print("Use case: Multi-level validation/transformation of runtime context")
    print()

    auth_middleware = AuthContextMiddleware()

    client = OpenAIChatClient(model_id="gpt-4o-mini")

    # Sub-agent with validation middleware
    protected_agent = client.as_agent(
        name="protected_agent",
        instructions="You perform protected operations that require authentication.",
        tools=[protected_operation],
        middleware=[auth_middleware.validate_and_track],
    )

    # Coordinator delegates to protected agent
    coordinator = client.as_agent(
        name="coordinator",
        instructions="You coordinate protected operations. Delegate to protected_executor.",
        tools=[
            protected_agent.as_tool(
                name="protected_executor",
                description="Execute protected operations",
            )
        ],
    )

    # Test with valid token
    print("Test 1: Valid token\n")
    await coordinator.run(
        "Execute operation: backup_database",
        api_token="valid-token-xyz-789",
        user_id="admin-123",
    )

    # Test with invalid token
    print("\nTest 2: Invalid token\n")
    await coordinator.run(
        "Execute operation: delete_records",
        api_token="invalid-token-bad",
        user_id="user-456",
    )

    print(f"\n[Validation Summary] Validated tokens: {len(auth_middleware.validated_tokens)}")
    print("✓ Pattern 3 complete - Middleware can validate/transform context at each level")


async def main() -> None:
    """Demonstrate all runtime context delegation patterns."""
    print("=" * 70)
    print("Runtime Context Delegation Patterns Demo")
    print("=" * 70)
    print()

    # Run Pattern 1
    await pattern_1_single_agent_with_closure()

    # Run Pattern 2
    await pattern_2_hierarchical_with_kwargs_propagation()

    # Run Pattern 3
    await pattern_3_hierarchical_with_middleware()


if __name__ == "__main__":
    asyncio.run(main())
