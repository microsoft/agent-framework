// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests for <see cref="WorkflowEvaluationExtensions.ExtractAgentData"/>.
/// </summary>
public sealed class WorkflowEvaluationTests
{
    [Fact]
    public void ExtractAgentData_EmptyEvents_ReturnsEmpty()
    {
        var result = WorkflowEvaluationExtensions.ExtractAgentData(new List<WorkflowEvent>(), splitter: null);

        Assert.Empty(result);
    }

    [Fact]
    public void ExtractAgentData_MatchedPair_ReturnsItem()
    {
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", "What is the weather?"),
            new ExecutorCompletedEvent("agent-1", "It's sunny."),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result);
        Assert.True(result.ContainsKey("agent-1"));
        Assert.Single(result["agent-1"]);
        Assert.Equal("What is the weather?", result["agent-1"][0].Query);
        Assert.Equal("It's sunny.", result["agent-1"][0].Response);
        Assert.Equal(2, result["agent-1"][0].Conversation.Count);
    }

    [Fact]
    public void ExtractAgentData_UnmatchedInvocation_NotIncluded()
    {
        // An invocation without a matching completion should not appear in results
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", "Hello"),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Empty(result);
    }

    [Fact]
    public void ExtractAgentData_CompletionWithoutInvocation_NotIncluded()
    {
        // A completion without a prior invocation should not appear in results
        var events = new List<WorkflowEvent>
        {
            new ExecutorCompletedEvent("agent-1", "Response"),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Empty(result);
    }

    [Fact]
    public void ExtractAgentData_MultipleAgents_SeparatedByExecutorId()
    {
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", "Q1"),
            new ExecutorInvokedEvent("agent-2", "Q2"),
            new ExecutorCompletedEvent("agent-1", "A1"),
            new ExecutorCompletedEvent("agent-2", "A2"),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Equal(2, result.Count);
        Assert.Equal("Q1", result["agent-1"][0].Query);
        Assert.Equal("A1", result["agent-1"][0].Response);
        Assert.Equal("Q2", result["agent-2"][0].Query);
        Assert.Equal("A2", result["agent-2"][0].Response);
    }

    [Fact]
    public void ExtractAgentData_DuplicateExecutorId_LastInvocationUsed()
    {
        // If the same executor is invoked twice before completing,
        // the second invocation overwrites the first
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", "First question"),
            new ExecutorInvokedEvent("agent-1", "Second question"),
            new ExecutorCompletedEvent("agent-1", "Answer"),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result);
        Assert.Single(result["agent-1"]);
        Assert.Equal("Second question", result["agent-1"][0].Query);
    }

    [Fact]
    public void ExtractAgentData_MultipleRoundsForSameExecutor_AllCaptured()
    {
        // Same executor invoked→completed twice (sequential rounds)
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", "Q1"),
            new ExecutorCompletedEvent("agent-1", "A1"),
            new ExecutorInvokedEvent("agent-1", "Q2"),
            new ExecutorCompletedEvent("agent-1", "A2"),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result); // one executor
        Assert.Equal(2, result["agent-1"].Count); // two items
        Assert.Equal("Q1", result["agent-1"][0].Query);
        Assert.Equal("Q2", result["agent-1"][1].Query);
    }

    [Fact]
    public void ExtractAgentData_NullData_UsesEmptyString()
    {
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", null!),
            new ExecutorCompletedEvent("agent-1", null),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result);
        Assert.Equal(string.Empty, result["agent-1"][0].Query);
        Assert.Equal(string.Empty, result["agent-1"][0].Response);
    }

    [Fact]
    public void ExtractAgentData_WithSplitter_SetOnItems()
    {
        var splitter = ConversationSplitters.LastTurn;
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", "Q"),
            new ExecutorCompletedEvent("agent-1", "A"),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter);

        Assert.Equal(splitter, result["agent-1"][0].Splitter);
    }
}
