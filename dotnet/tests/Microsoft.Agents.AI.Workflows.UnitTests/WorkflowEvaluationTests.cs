// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

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

    [Fact]
    public void ExtractAgentData_ChatMessageData_ExtractsText()
    {
        // When Data is a ChatMessage, the fix should extract .Text instead of type name
        var queryMsg = new ChatMessage(ChatRole.User, "What is the weather?");
        var responseMsg = new ChatMessage(ChatRole.Assistant, "It's sunny.");
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", queryMsg),
            new ExecutorCompletedEvent("agent-1", responseMsg),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result);
        Assert.Equal("What is the weather?", result["agent-1"][0].Query);
        Assert.Equal("It's sunny.", result["agent-1"][0].Response);
    }

    [Fact]
    public void ExtractAgentData_ChatMessageListData_ExtractsLastUserText()
    {
        // When Data is IReadOnlyList<ChatMessage>, extract last user message text
        IReadOnlyList<ChatMessage> messages = new List<ChatMessage>
        {
            new(ChatRole.User, "First question"),
            new(ChatRole.Assistant, "First answer"),
            new(ChatRole.User, "Follow-up question"),
        };

        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", messages),
            new ExecutorCompletedEvent("agent-1", "Response text"),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result);
        Assert.Equal("Follow-up question", result["agent-1"][0].Query);
    }

    [Fact]
    public void ExtractAgentData_AgentResponseData_ExtractsText()
    {
        // When completed Data is an AgentResponse, extract .Text
        var agentResponse = new AgentResponse(new ChatMessage(ChatRole.Assistant, "Agent says hello"));
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", "Hi there"),
            new ExecutorCompletedEvent("agent-1", agentResponse),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result);
        Assert.Equal("Hi there", result["agent-1"][0].Query);
        Assert.Equal("Agent says hello", result["agent-1"][0].Response);
    }

    [Fact]
    public void ExtractAgentData_AgentResponseData_PreservesFullMessages()
    {
        // When completed Data is an AgentResponse, the conversation should include
        // all response messages (tool calls, intermediate, etc.) not just a text summary
        var toolCallMsg = new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call_1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" })]);
        var toolResultMsg = new ChatMessage(ChatRole.Tool, [new FunctionResultContent("call_1", "Sunny, 72°F")]);
        var finalMsg = new ChatMessage(ChatRole.Assistant, "It's sunny and 72°F in Seattle.");
        var agentResponse = new AgentResponse
        {
            Messages = [toolCallMsg, toolResultMsg, finalMsg],
        };

        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", "What's the weather?"),
            new ExecutorCompletedEvent("agent-1", agentResponse),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        // Should have user query + all 3 response messages
        Assert.Equal(4, result["agent-1"][0].Conversation.Count);
        Assert.Equal(ChatRole.User, result["agent-1"][0].Conversation[0].Role);
        Assert.Equal(ChatRole.Assistant, result["agent-1"][0].Conversation[1].Role);
        Assert.Equal(ChatRole.Tool, result["agent-1"][0].Conversation[2].Role);
        Assert.Equal(ChatRole.Assistant, result["agent-1"][0].Conversation[3].Role);
    }

    [Fact]
    public void ExtractAgentData_UnknownObjectData_UsesToString()
    {
        // When Data is an unknown object type, the ToString() fallback should produce
        // the string representation (not a type name for known types)
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("agent-1", 42),
            new ExecutorCompletedEvent("agent-1", 3.14),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result);
        Assert.Equal("42", result["agent-1"][0].Query);
        Assert.Equal("3.14", result["agent-1"][0].Response);
    }

    [Fact]
    public void ExtractAgentData_SkipsInternalExecutors()
    {
        var events = new List<WorkflowEvent>
        {
            new ExecutorInvokedEvent("_internal", "internal query"),
            new ExecutorCompletedEvent("_internal", "internal response"),
            new ExecutorInvokedEvent("input-conversation", "start"),
            new ExecutorCompletedEvent("input-conversation", "done"),
            new ExecutorInvokedEvent("end-conversation", "end query"),
            new ExecutorCompletedEvent("end-conversation", "end response"),
            new ExecutorInvokedEvent("end", "end query"),
            new ExecutorCompletedEvent("end", "end response"),
            new ExecutorInvokedEvent("real-agent", "real query"),
            new ExecutorCompletedEvent("real-agent", "real response"),
        };

        var result = WorkflowEvaluationExtensions.ExtractAgentData(events, splitter: null);

        Assert.Single(result);
        Assert.True(result.ContainsKey("real-agent"));
        Assert.DoesNotContain("_internal", result.Keys);
        Assert.DoesNotContain("input-conversation", result.Keys);
        Assert.DoesNotContain("end-conversation", result.Keys);
        Assert.DoesNotContain("end", result.Keys);
    }

    // ---------------------------------------------------------------
    // EvaluateAsync integration test
    // ---------------------------------------------------------------

    [Fact]
    public async Task EvaluateAsync_WithSequentialWorkflow_ReturnsPerAgentSubResultsAsync()
    {
        // Arrange: two agents in a sequential workflow
        var agent1 = new TestEchoAgent(name: "agent-one");
        var agent2 = new TestEchoAgent(name: "agent-two");
        var workflow = AgentWorkflowBuilder.BuildSequential(agent1, agent2);
        var input = new List<ChatMessage> { new(ChatRole.User, "Hello world") };

        var evaluator = new LocalEvaluator(
            FunctionEvaluator.Create("has_content", (EvalItem item) => item.Conversation.Count > 0));

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, input);
        var results = await run.EvaluateAsync(evaluator, includeOverall: false, includePerAgent: true);

        // Assert — results returned
        Assert.NotNull(results);

        // Assert — per-agent sub-results are populated
        Assert.NotNull(results.SubResults);
        Assert.True(results.SubResults.Count >= 2, $"Expected at least 2 agent sub-results, got {results.SubResults.Count}");

        // Each sub-result should have evaluated items
        foreach (var (agentId, subResult) in results.SubResults)
        {
            Assert.True(subResult.Total > 0, $"Agent '{agentId}' should have at least one evaluated item");
        }
    }
}
