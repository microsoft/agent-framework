// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class HandoffMessageFilterTests
{
    private List<ChatMessage> CreateTestMessages(bool firstAgentUsesCallId, bool secondAgentUsesCallId, HandoffToolCallFilteringBehavior filter = HandoffToolCallFilteringBehavior.None)
    {
        FunctionCallContent handoffRequest1 = CreateHandoffCall(1, firstAgentUsesCallId);
        FunctionResultContent handoffResponse1 = CreateHandoffResponse(handoffRequest1);

        FunctionCallContent toolCall = CreateToolCall(secondAgentUsesCallId);
        FunctionResultContent toolResponse = CreateToolResponse(toolCall);

        // Approvals come from the function call middleware over ChatClient, so we can expect there to be a RequestId (not that we
        // care, because we do not filter approval content)
        ToolApprovalRequestContent toolApproval = new(Guid.NewGuid().ToString("N"), toolCall);
        ToolApprovalResponseContent toolApprovalResponse = new(toolApproval.RequestId, true, toolCall);

        FunctionCallContent handoffRequest2 = CreateHandoffCall(1, secondAgentUsesCallId);
        FunctionResultContent handoffResponse2 = CreateHandoffResponse(handoffRequest2);

        List<ChatMessage> result = [new(ChatRole.User, "Hello")];

        // Agent 1 turn
        result.Add(new(ChatRole.Assistant, "Hello! What do you want help with today?"));
        result.Add(new(ChatRole.User, "Please explain temperature"));

        // Unless we are filtering none, we expect the handoff call to be filtered out, so we add it conditionally
        if (filter == HandoffToolCallFilteringBehavior.None)
        {
            result.Add(new(ChatRole.Assistant, [handoffRequest1]));
            result.Add(new(ChatRole.Tool, [handoffResponse1]));
        }

        // Agent 2 turn

        // Tool approvals are never filtered, so we add them unconditionally
        result.Add(new(ChatRole.Assistant, [toolApproval]));
        result.Add(new(ChatRole.User, [toolApprovalResponse]));

        // Unless we are filtering all, we expect the tool call to be retained, so we add it conditionally
        if (filter != HandoffToolCallFilteringBehavior.All)
        {
            result.Add(new(ChatRole.Assistant, [toolCall]));
            result.Add(new(ChatRole.Tool, [toolResponse]));
        }

        result.Add(new(ChatRole.Assistant, "Temperature is a measure of the average kinetic energy of the particles in a substance."));

        if (filter == HandoffToolCallFilteringBehavior.None)
        {
            result.Add(new(ChatRole.Assistant, [handoffRequest2]));
            result.Add(new(ChatRole.Tool, [handoffResponse2]));
        }

        return result;
    }

    private static FunctionCallContent CreateHandoffCall(int id, bool useCallId)
    {
        string callName = $"{HandoffWorkflowBuilder.FunctionPrefix}{id}";
        string callId = useCallId ? Guid.NewGuid().ToString("N") : callName;

        return new FunctionCallContent(callId, callName);
    }

    private static FunctionResultContent CreateHandoffResponse(FunctionCallContent call)
        => HandoffAgentExecutor.CreateHandoffResult(call.CallId);

    private static FunctionCallContent CreateToolCall(bool useCallId)
    {
        const string CallName = "ToolFunction";
        string callId = useCallId ? Guid.NewGuid().ToString("N") : CallName;

        return new FunctionCallContent(callId, CallName);
    }

    private static FunctionResultContent CreateToolResponse(FunctionCallContent call)
        => new(call.CallId, new object());

    [Theory]
    [InlineData(true, true, HandoffToolCallFilteringBehavior.None)]
    [InlineData(true, false, HandoffToolCallFilteringBehavior.None)]
    [InlineData(false, true, HandoffToolCallFilteringBehavior.None)]
    [InlineData(false, false, HandoffToolCallFilteringBehavior.None)]
    [InlineData(true, true, HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(true, false, HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(false, true, HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(false, false, HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(true, true, HandoffToolCallFilteringBehavior.All)]
    [InlineData(true, false, HandoffToolCallFilteringBehavior.All)]
    [InlineData(false, true, HandoffToolCallFilteringBehavior.All)]
    [InlineData(false, false, HandoffToolCallFilteringBehavior.All)]
    public void Test_HandoffMessageFilter_FiltersOnlyExpectedMessages(bool firstAgentUsesCallId, bool secondAgentUsesCallId, HandoffToolCallFilteringBehavior behavior)
    {
        // Arrange
        List<ChatMessage> messages = this.CreateTestMessages(firstAgentUsesCallId, secondAgentUsesCallId);
        List<ChatMessage> expected = this.CreateTestMessages(firstAgentUsesCallId, secondAgentUsesCallId, behavior);

        HandoffMessagesFilter filter = new(behavior);

        // Act
        IEnumerable<ChatMessage> filteredMessages = filter.FilterMessages(messages);

        // Assert
        filteredMessages.Should().BeEquivalentTo(expected);
    }
}
