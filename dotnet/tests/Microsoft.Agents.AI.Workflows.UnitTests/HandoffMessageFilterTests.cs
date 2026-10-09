// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class HandoffMessageFilterTests
{
    private List<ChatMessage> CreateTestMessages(bool firstAgentUsesCallId, bool secondAgentUsesCallId, HandoffToolCallFilteringBehavior filter = HandoffToolCallFilteringBehavior.None)
    {
        FunctionCallContent handoffRequest1 = CreateHandoffCall(1, firstAgentUsesCallId, "first");
        FunctionResultContent handoffResponse1 = CreateHandoffResponse(handoffRequest1);

        FunctionCallContent toolCall = CreateToolCall(secondAgentUsesCallId, "tool");
        FunctionResultContent toolResponse = CreateToolResponse(toolCall);

        // Approvals come from the function call middleware over ChatClient, so we can expect there to be a RequestId (not that we
        // care, because we do not filter approval content)
        ToolApprovalRequestContent toolApproval = new("approval_request", toolCall);
        ToolApprovalResponseContent toolApprovalResponse = new(toolApproval.RequestId, true, toolCall);

        FunctionCallContent handoffRequest2 = CreateHandoffCall(1, secondAgentUsesCallId, "second");
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

    private static FunctionCallContent CreateHandoffCall(int id, bool useCallId, string callIdSuffix)
    {
        string callName = $"{HandoffWorkflowBuilder.FunctionPrefix}{id}";
        string callId = useCallId ? $"{callName}_{callIdSuffix}" : callName;

        return new FunctionCallContent(callId, callName);
    }

    private static FunctionResultContent CreateHandoffResponse(FunctionCallContent call)
        => HandoffAgentExecutor.CreateHandoffResult(call.CallId);

    private static FunctionCallContent CreateToolCall(bool useCallId, string callIdSuffix)
    {
        const string CallName = "ToolFunction";
        string callId = useCallId ? $"{CallName}_{callIdSuffix}" : CallName;

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
        List<ChatMessage> filteredMessages = [.. filter.FilterMessages(messages)];

        // Assert
        Assert.Equal(expected.Count, filteredMessages.Count);
        for (int i = 0; i < expected.Count; i++)
        {
            AssertMessageShape(expected[i], filteredMessages[i]);
        }
    }

    [Theory]
    [InlineData(false, HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(true, HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(false, HandoffToolCallFilteringBehavior.All)]
    [InlineData(true, HandoffToolCallFilteringBehavior.All)]
    public void Test_HandoffMessageFilter_DropsReasoningOnlyHandoffMessages(bool includeReasoning, HandoffToolCallFilteringBehavior behavior)
    {
        // Arrange
        // Regression test for issue #7384: reasoning must not leave a handoff message after the user's request.
        ChatMessage userMessage = new(ChatRole.User, "What is the status of my order?");
        FunctionCallContent handoffCall = CreateHandoffCall(1, useCallId: true, callIdSuffix: "triage");
        ChatMessage handoffMessage = new(ChatRole.Assistant, [handoffCall]);
        if (includeReasoning)
        {
            handoffMessage.Contents.Insert(0, new TextReasoningContent("The orders specialist should answer this request."));
        }

        List<ChatMessage> messages =
        [
            userMessage,
            handoffMessage,
            new(ChatRole.Tool, [CreateHandoffResponse(handoffCall)]),
        ];
        HandoffMessagesFilter filter = new(behavior);

        // Act
        List<ChatMessage> filteredMessages = [.. filter.FilterMessages(messages)];

        // Assert
        AssertMessageShape(userMessage, Assert.Single(filteredMessages));
        Assert.Contains(handoffCall, handoffMessage.Contents);
        Assert.Equal(includeReasoning ? 2 : 1, handoffMessage.Contents.Count);
    }

    [Theory]
    [InlineData(HandoffToolCallFilteringBehavior.None)]
    [InlineData(HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(HandoffToolCallFilteringBehavior.All)]
    public void Test_HandoffMessageFilter_PreservesStandaloneReasoning(HandoffToolCallFilteringBehavior behavior)
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant, [new TextReasoningContent("Thinking about the user's request.")]);
        HandoffMessagesFilter filter = new(behavior);

        // Act
        List<ChatMessage> filteredMessages = [.. filter.FilterMessages([message])];

        // Assert
        AssertMessageShape(message, Assert.Single(filteredMessages));
    }

    [Theory]
    [InlineData(HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(HandoffToolCallFilteringBehavior.All)]
    public void Test_HandoffMessageFilter_PreservesTextAlongsideFilteredHandoffReasoning(HandoffToolCallFilteringBehavior behavior)
    {
        // Arrange
        TextReasoningContent reasoning = new("The orders specialist should answer this request.");
        TextContent text = new("I will transfer you to the orders specialist.");
        FunctionCallContent handoffCall = CreateHandoffCall(1, useCallId: true, callIdSuffix: "triage");
        ChatMessage message = new(ChatRole.Assistant, [reasoning, text, handoffCall]);
        HandoffMessagesFilter filter = new(behavior);

        // Act
        List<ChatMessage> filteredMessages = [.. filter.FilterMessages(
            [message, new(ChatRole.Tool, [CreateHandoffResponse(handoffCall)])])];

        // Assert
        AssertMessageShape(new(ChatRole.Assistant, [reasoning, text]), Assert.Single(filteredMessages));
        Assert.Equal(3, message.Contents.Count);
        Assert.Contains(handoffCall, message.Contents);
    }

    [Theory]
    [InlineData(false, HandoffToolCallFilteringBehavior.None)]
    [InlineData(true, HandoffToolCallFilteringBehavior.None)]
    [InlineData(false, HandoffToolCallFilteringBehavior.HandoffOnly)]
    [InlineData(false, HandoffToolCallFilteringBehavior.All)]
    [InlineData(true, HandoffToolCallFilteringBehavior.All)]
    public void Test_HandoffMessageFilter_ReasoningFollowsToolFiltering(bool isHandoff, HandoffToolCallFilteringBehavior behavior)
    {
        // Arrange
        FunctionCallContent call = isHandoff
            ? CreateHandoffCall(1, useCallId: true, callIdSuffix: "triage")
            : CreateToolCall(useCallId: true, callIdSuffix: "orders");
        List<ChatMessage> messages =
        [
            new(ChatRole.Assistant, [new TextReasoningContent("Checking the order status."), call]),
            new(ChatRole.Tool, [new FunctionResultContent(call.CallId, "Order shipped.")]),
        ];
        HandoffMessagesFilter filter = new(behavior);

        // Act
        List<ChatMessage> filteredMessages = [.. filter.FilterMessages(messages)];

        // Assert
        if (behavior == HandoffToolCallFilteringBehavior.All)
        {
            Assert.Empty(filteredMessages);
        }
        else
        {
            Assert.Equal(messages.Count, filteredMessages.Count);
            for (int i = 0; i < messages.Count; i++)
            {
                AssertMessageShape(messages[i], filteredMessages[i]);
            }
        }
    }

    private static void AssertMessageShape(ChatMessage expected, ChatMessage actual)
    {
        Assert.Equal(expected.Role, actual.Role);
        Assert.Equal(expected.Text, actual.Text);
        Assert.Equal(expected.Contents.Count, actual.Contents.Count);

        for (int i = 0; i < expected.Contents.Count; i++)
        {
            AIContent expectedContent = expected.Contents[i];
            AIContent actualContent = actual.Contents[i];
            Assert.Equal(expectedContent.GetType(), actualContent.GetType());

            if (expectedContent is FunctionCallContent expectedCall && actualContent is FunctionCallContent actualCall)
            {
                AssertFunctionCallContent(expectedCall, actualCall);
            }
            else if (expectedContent is FunctionResultContent expectedResult && actualContent is FunctionResultContent actualResult)
            {
                Assert.Equal(expectedResult.CallId, actualResult.CallId);
                Assert.Equivalent(expectedResult.Result, actualResult.Result);
            }
            else if (expectedContent is ToolApprovalRequestContent expectedApprovalRequest && actualContent is ToolApprovalRequestContent actualApprovalRequest)
            {
                Assert.Equal(expectedApprovalRequest.RequestId, actualApprovalRequest.RequestId);
                AssertFunctionCallContent(
                    Assert.IsType<FunctionCallContent>(expectedApprovalRequest.ToolCall),
                    Assert.IsType<FunctionCallContent>(actualApprovalRequest.ToolCall));
            }
            else if (expectedContent is ToolApprovalResponseContent expectedApprovalResponse && actualContent is ToolApprovalResponseContent actualApprovalResponse)
            {
                Assert.Equal(expectedApprovalResponse.RequestId, actualApprovalResponse.RequestId);
                Assert.Equal(expectedApprovalResponse.Approved, actualApprovalResponse.Approved);
                AssertFunctionCallContent(
                    Assert.IsType<FunctionCallContent>(expectedApprovalResponse.ToolCall),
                    Assert.IsType<FunctionCallContent>(actualApprovalResponse.ToolCall));
            }
            else
            {
                Assert.Equivalent(expectedContent, actualContent);
            }
        }
    }

    private static void AssertFunctionCallContent(FunctionCallContent expected, FunctionCallContent actual)
    {
        Assert.Equal(expected.CallId, actual.CallId);
        Assert.Equal(expected.Name, actual.Name);
        Assert.Equivalent(expected.Arguments, actual.Arguments);
    }
}
