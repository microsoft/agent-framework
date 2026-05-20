// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="OutputConverter"/> driven directly by hand-crafted update
/// sequences that mirror the patterns produced by real workflow executions
/// (sequential, group chat, code executor, sub-workflow, mixed content types).
/// </summary>
public class OutputConverterWorkflowTests
{
    [Fact]
    public async Task SequentialWorkflowPattern_ProducesCorrectEventsAsync()
    {
        // Simulate what WorkflowSession produces for a 2-agent sequential workflow
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            // Superstep 1: Agent 1
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(1) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_1", "start") },
            new AgentResponseUpdate { MessageId = "msg_a1", Contents = [new MeaiTextContent("Agent 1 output")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("agent_1", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(1) },
            // Superstep 2: Agent 2
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(2) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("agent_2", "start") },
            new AgentResponseUpdate { MessageId = "msg_a2", Contents = [new MeaiTextContent("Agent 2 output")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("agent_2", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(2) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // 4 workflow action items + 2 text messages = 6 output items
        Assert.Equal(6, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Equal(2, events.OfType<ResponseTextDeltaEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    [Fact]
    public async Task GroupChatPattern_ProducesCorrectEventsAsync()
    {
        // Simulate round-robin group chat: agent1 → agent2 → agent1 → terminate
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(1) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("chat_agent_1", "turn") },
            new AgentResponseUpdate { MessageId = "msg_gc_1", Contents = [new MeaiTextContent("Agent 1 turn 1")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("chat_agent_1", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(1) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(2) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("chat_agent_2", "turn") },
            new AgentResponseUpdate { MessageId = "msg_gc_2", Contents = [new MeaiTextContent("Agent 2 turn 1")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("chat_agent_2", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(2) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(3) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("chat_agent_1", "turn") },
            new AgentResponseUpdate { MessageId = "msg_gc_3", Contents = [new MeaiTextContent("Agent 1 turn 2")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("chat_agent_1", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(3) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // 6 workflow actions + 3 text messages = 9 output items
        Assert.Equal(9, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Equal(3, events.OfType<ResponseTextDeltaEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    [Fact]
    public async Task CodeExecutorPattern_ProducesCorrectEventsAsync()
    {
        // Simulate a code-based FunctionExecutor: invoked → completed, no text content
        // (code executors don't produce AgentResponseUpdateEvent, just executor lifecycle)
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(1) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("uppercase_fn", "hello") },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("uppercase_fn", "HELLO") },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(1) },
            // Second executor uses the output
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(2) },
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("format_agent", "start") },
            new AgentResponseUpdate { MessageId = "msg_fmt", Contents = [new MeaiTextContent("Formatted: HELLO")] },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("format_agent", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(2) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // 4 workflow actions + 1 text message = 5 output items
        Assert.Equal(5, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Single(events.OfType<ResponseTextDeltaEvent>());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    [Fact]
    public async Task SubworkflowPattern_ProducesCorrectEventsAsync()
    {
        // Simulate a parent workflow that invokes a sub-workflow executor
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new WorkflowStartedEvent("parent") },
            new AgentResponseUpdate { RawRepresentation = new SuperStepStartedEvent(1) },
            // Sub-workflow executor invoked
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("sub_workflow_host", "start") },
            // Inner agent within sub-workflow produces text (unwrapped by WorkflowSession)
            new AgentResponseUpdate { MessageId = "msg_sub_1", Contents = [new MeaiTextContent("Sub-workflow agent output")] },
            // Sub-workflow executor completed
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("sub_workflow_host", null) },
            new AgentResponseUpdate { RawRepresentation = new SuperStepCompletedEvent(1) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // 2 workflow actions + 1 text message = 3 output items
        Assert.Equal(3, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Single(events.OfType<ResponseTextDeltaEvent>());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    [Fact]
    public async Task WorkflowWithMultipleContentTypes_HandlesAllCorrectlyAsync()
    {
        // Simulate a workflow producing reasoning, text, function calls, and usage
        var (stream, _) = CreateTestStream();
        var updates = new[]
        {
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("planner", "start") },
            // Reasoning
            new AgentResponseUpdate { Contents = [new TextReasoningContent("Let me think about this...")] },
            // Function call (tool use)
            new AgentResponseUpdate
            {
                Contents = [new FunctionCallContent("call_search", "web_search",
                    new Dictionary<string, object?> { ["query"] = "latest news" })]
            },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("planner", null) },
            // Next executor uses tool result
            new AgentResponseUpdate { RawRepresentation = new ExecutorInvokedEvent("writer", "start") },
            new AgentResponseUpdate { MessageId = "msg_w1", Contents = [new MeaiTextContent("Based on my research, ")] },
            new AgentResponseUpdate { MessageId = "msg_w1", Contents = [new MeaiTextContent("here are the findings.")] },
            new AgentResponseUpdate
            {
                Contents = [new UsageContent(new UsageDetails { InputTokenCount = 500, OutputTokenCount = 200, TotalTokenCount = 700 })]
            },
            new AgentResponseUpdate { RawRepresentation = new ExecutorCompletedEvent("writer", null) },
        };

        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in OutputConverter.ConvertUpdatesToEventsAsync(ToAsync(updates), stream))
        {
            events.Add(evt);
        }

        // Workflow actions: 4 (2 invoked + 2 completed)
        // Content: 1 reasoning + 1 function_call (lone FCC = HITL request) + 1 text = 3
        // Total: 7 output items
        Assert.Equal(7, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Single(events.OfType<ResponseFunctionCallArgumentsDoneEvent>());
        Assert.Equal(2, events.OfType<ResponseTextDeltaEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    private static (ResponseEventStream stream, Mock<ResponseContext> mockContext) CreateTestStream()
    {
        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        var request = new CreateResponse { Model = "test-model" };
        var stream = new ResponseEventStream(mockContext.Object, request);
        return (stream, mockContext);
    }

    private static async IAsyncEnumerable<T> ToAsync<T>(IEnumerable<T> source)
    {
        foreach (var item in source)
        {
            yield return item;
        }

        await Task.CompletedTask;
    }
}
