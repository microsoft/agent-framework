# Copyright (c) Microsoft. All rights reserved.

"""Additional test cases for WorkflowAgent user input filtering.

These tests address review feedback from moonbox3 on PR #4275:
1. Verify author_name is preserved through filtering
2. Verify non-assistant, non-user roles (system, tool) are also filtered
3. Non-streaming edge case for empty-after-filtering
"""

from typing_extensions import Never

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)


class TestWorkflowAgentUserInputFilteringAdditional:
    """Additional filtering tests addressing PR #4275 review feedback."""

    async def test_streaming_author_name_preserved_through_filtering(self):
        """Test that author_name is correctly propagated through filtering.

        Addresses moonbox3's suggestion to verify that the production code's
        `author_name=msg.author_name` mapping is preserved when non-assistant
        messages are filtered out.
        """

        @executor
        async def groupchat_like_executor(
            messages: list[Message], ctx: WorkflowContext[Never, AgentResponse]
        ) -> None:
            response = AgentResponse(
                messages=[
                    Message(role="user", text="hi"),
                    Message(role="assistant", text="Hello! How can I help?", author_name="Principal"),
                    Message(role="user", text="what is 2+2?"),
                    Message(role="assistant", text="2+2 = 4", author_name="Maths Teacher"),
                    Message(role="assistant", text="The answer is 4.", author_name="Principal"),
                ],
            )
            await ctx.yield_output(response)

        workflow = WorkflowBuilder(start_executor=groupchat_like_executor).build()
        agent = workflow.as_agent("groupchat-agent")

        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("hi", stream=True):
            updates.append(update)

        # Should only have assistant messages (3 out of 5)
        assert len(updates) == 3, f"Expected 3 assistant updates, got {len(updates)}"

        # Verify all updates are assistant role
        for update in updates:
            assert update.role == "assistant", f"Expected role='assistant', got role='{update.role}'"

        # Verify author_name is propagated correctly
        assert updates[0].author_name == "Principal"
        assert updates[1].author_name == "Maths Teacher"
        assert updates[2].author_name == "Principal"

    async def test_streaming_filters_system_and_tool_roles(self):
        """Test that non-assistant, non-user roles (system, tool) are also filtered.

        The filter uses an allowlist (role == "assistant") rather than a blocklist,
        so system and tool messages should also be excluded from the output.
        This is intentional: WorkflowAgent output should only contain assistant
        messages. System prompts and tool results are internal workflow artifacts.
        """

        @executor
        async def mixed_roles_executor(
            messages: list[Message], ctx: WorkflowContext[Never, AgentResponse]
        ) -> None:
            response = AgentResponse(
                messages=[
                    Message(role="system", text="You are a helpful assistant."),
                    Message(role="user", text="What is the weather?"),
                    Message(role="assistant", text="Let me check the weather for you."),
                    Message(role="tool", text="Weather API result: Sunny, 72°F"),
                    Message(role="assistant", text="It's sunny and 72°F today!"),
                ],
            )
            await ctx.yield_output(response)

        workflow = WorkflowBuilder(start_executor=mixed_roles_executor).build()
        agent = workflow.as_agent("mixed-roles-agent")

        # Test streaming path
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("weather?", stream=True):
            updates.append(update)

        # Only assistant messages should pass through (2 out of 5)
        assert len(updates) == 2, f"Expected 2 assistant updates, got {len(updates)}"
        texts = [u.text for u in updates]
        assert texts == ["Let me check the weather for you.", "It's sunny and 72°F today!"]

        # Verify system and tool messages are NOT present
        for update in updates:
            assert update.role == "assistant"

    async def test_non_streaming_filters_system_and_tool_roles(self):
        """Test non-streaming path also filters system and tool roles."""

        @executor
        async def mixed_roles_executor(
            messages: list[Message], ctx: WorkflowContext[Never, AgentResponse]
        ) -> None:
            response = AgentResponse(
                messages=[
                    Message(role="system", text="System prompt"),
                    Message(role="user", text="Hello"),
                    Message(role="assistant", text="Hi there!"),
                    Message(role="tool", text="tool output"),
                ],
            )
            await ctx.yield_output(response)

        workflow = WorkflowBuilder(start_executor=mixed_roles_executor).build()
        agent = workflow.as_agent("mixed-roles-agent")

        result = await agent.run("hello")

        # Only the assistant message should remain
        assert len(result.messages) == 1, f"Expected 1 message, got {len(result.messages)}"
        assert result.messages[0].text == "Hi there!"
        assert result.messages[0].role == "assistant"

    async def test_non_streaming_empty_after_filtering(self):
        """Test non-streaming path handles AgentResponse with only non-assistant messages.

        Verifies that when all messages are filtered out in the non-streaming path,
        the result contains an empty messages list without crashing.
        """

        @executor
        async def non_assistant_only_executor(
            messages: list[Message], ctx: WorkflowContext[Never, AgentResponse]
        ) -> None:
            response = AgentResponse(
                messages=[
                    Message(role="user", text="user msg"),
                    Message(role="system", text="system msg"),
                    Message(role="tool", text="tool msg"),
                ],
            )
            await ctx.yield_output(response)

        workflow = WorkflowBuilder(start_executor=non_assistant_only_executor).build()
        agent = workflow.as_agent("non-assistant-only-agent")

        result = await agent.run("test")

        # All messages filtered out — should be empty, not crash
        assert len(result.messages) == 0, f"Expected 0 messages, got {len(result.messages)}"
