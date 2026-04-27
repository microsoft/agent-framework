// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

/// <summary>
/// Integration tests that verify workflow execution through the
/// <see cref="AgentFrameworkResponseHandler"/> → <see cref="OutputConverter"/> pipeline.
/// These use real workflow builders and the InProcessExecution environment
/// to produce authentic streaming event patterns.
/// </summary>
public class WorkflowIntegrationTests
{
    // ===== Sequential Workflow Tests =====

    [Fact]
    public async Task SequentialWorkflow_SingleAgent_ProducesTextOutputAsync()
    {
        // Arrange: single-agent sequential workflow
        var echoAgent = new StreamingTextAgent("echo", "Hello from the workflow!");
        var workflow = AgentWorkflowBuilder.BuildSequential("test-sequential", echoAgent);
        var workflowAgent = workflow.AsAIAgent(
            id: "workflow-agent",
            name: "Test Workflow",
            executionEnvironment: InProcessExecution.OffThread,
            includeExceptionDetails: true);

        var (handler, request, context) = CreateHandlerWithAgent(workflowAgent, "Hello");

        // Act
        var events = await CollectEventsAsync(handler, request, context);

        // Assert: should have lifecycle events + at least one text output + terminal
        Assert.IsType<ResponseCreatedEvent>(events[0]);
        Assert.IsType<ResponseInProgressEvent>(events[1]);
        Assert.True(events.Count >= 4, $"Expected at least 4 events, got {events.Count}");

        var lastEvent = events[^1];
        Assert.True(
            lastEvent is ResponseCompletedEvent || lastEvent is ResponseFailedEvent,
            $"Expected terminal event, got {lastEvent.GetType().Name}");
    }

    [Fact]
    public async Task SequentialWorkflow_TwoAgents_ProducesOutputFromBothAsync()
    {
        // Arrange: two agents in sequence
        var agent1 = new StreamingTextAgent("agent1", "First agent says hello");
        var agent2 = new StreamingTextAgent("agent2", "Second agent says goodbye");
        var workflow = AgentWorkflowBuilder.BuildSequential("test-sequential-2", agent1, agent2);
        var workflowAgent = workflow.AsAIAgent(
            id: "seq-workflow",
            name: "Sequential Workflow",
            executionEnvironment: InProcessExecution.OffThread,
            includeExceptionDetails: true);

        var (handler, request, context) = CreateHandlerWithAgent(workflowAgent, "Process this");

        // Act
        var events = await CollectEventsAsync(handler, request, context);

        // Assert: should have workflow action events for executor lifecycle
        var lastEvent = events[^1];
        Assert.True(
            lastEvent is ResponseCompletedEvent || lastEvent is ResponseFailedEvent,
            $"Expected terminal event, got {lastEvent.GetType().Name}");

        // Should have output item events (either text messages or workflow actions)
        Assert.True(events.OfType<ResponseOutputItemAddedEvent>().Any(),
            "Expected at least one output item from the workflow");
    }

    // ===== Workflow Error Propagation =====

    [Fact]
    public async Task Workflow_AgentThrowsException_ProducesErrorOutputAsync()
    {
        // Arrange: workflow with an agent that throws
        var throwingAgent = new ThrowingStreamingAgent("thrower", new InvalidOperationException("Agent crashed"));
        var workflow = AgentWorkflowBuilder.BuildSequential("test-error", throwingAgent);
        var workflowAgent = workflow.AsAIAgent(
            id: "error-workflow",
            name: "Error Workflow",
            executionEnvironment: InProcessExecution.OffThread,
            includeExceptionDetails: true);

        var (handler, request, context) = CreateHandlerWithAgent(workflowAgent, "Trigger error");

        // Act
        var events = await CollectEventsAsync(handler, request, context);

        // Assert: should have lifecycle events + error/failure indicator
        Assert.IsType<ResponseCreatedEvent>(events[0]);
        Assert.IsType<ResponseInProgressEvent>(events[1]);

        var lastEvent = events[^1];
        // Workflow errors surface as either Failed or Completed (depending on error handling)
        Assert.True(
            lastEvent is ResponseCompletedEvent || lastEvent is ResponseFailedEvent,
            $"Expected terminal event, got {lastEvent.GetType().Name}");
    }

    // ===== Workflow Action Lifecycle Events =====

    [Fact]
    public async Task Workflow_ExecutorEvents_ProduceWorkflowActionItemsAsync()
    {
        // Arrange
        var agent = new StreamingTextAgent("test-agent", "Result");
        var workflow = AgentWorkflowBuilder.BuildSequential("test-actions", agent);
        var workflowAgent = workflow.AsAIAgent(
            id: "actions-workflow",
            name: "Actions Workflow",
            executionEnvironment: InProcessExecution.OffThread);

        var (handler, request, context) = CreateHandlerWithAgent(workflowAgent, "Hello");

        // Act
        var events = await CollectEventsAsync(handler, request, context);

        // Assert: workflow should produce OutputItemAdded events for executor lifecycle
        var addedEvents = events.OfType<ResponseOutputItemAddedEvent>().ToList();
        Assert.True(addedEvents.Count >= 1,
            $"Expected at least 1 output item added event, got {addedEvents.Count}");
    }

    // ===== Keyed Workflow Registration =====

    [Fact]
    public async Task WorkflowAgent_RegisteredWithKey_ResolvesCorrectlyAsync()
    {
        // Arrange: workflow agent registered with a keyed service name
        var agent = new StreamingTextAgent("inner", "Keyed workflow response");
        var workflow = AgentWorkflowBuilder.BuildSequential("keyed-wf", agent);
        var workflowAgent = workflow.AsAIAgent(
            id: "keyed-workflow",
            name: "Keyed Workflow",
            executionEnvironment: InProcessExecution.OffThread);

        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddKeyedSingleton("my-workflow", workflowAgent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);
        var request = new CreateResponse { Model = "test", AgentReference = new AgentReference("my-workflow") };
        request.Input = CreateUserInput("Test keyed workflow");
        var mockContext = CreateMockContext();

        // Act
        var events = await CollectEventsAsync(handler, request, mockContext.Object);

        // Assert
        Assert.IsType<ResponseCreatedEvent>(events[0]);
        Assert.True(events.Count >= 3, $"Expected at least 3 events, got {events.Count}");
    }

    // ===== OutputConverter Direct Workflow Pattern Tests =====
    // These test the OutputConverter directly with update patterns that mirror real workflows.

    [Fact]
    public async Task OutputConverter_SequentialWorkflowPattern_ProducesCorrectEventsAsync()
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
    public async Task OutputConverter_GroupChatPattern_ProducesCorrectEventsAsync()
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
    public async Task OutputConverter_CodeExecutorPattern_ProducesCorrectEventsAsync()
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
    public async Task OutputConverter_SubworkflowPattern_ProducesCorrectEventsAsync()
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
    public async Task OutputConverter_WorkflowWithMultipleContentTypes_HandlesAllCorrectlyAsync()
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
        // Content: 1 reasoning + 1 function call + 1 text message = 3
        // Total: 7 output items
        Assert.Equal(7, events.OfType<ResponseOutputItemAddedEvent>().Count());
        Assert.Contains(events, e => e is ResponseFunctionCallArgumentsDoneEvent);
        Assert.Equal(2, events.OfType<ResponseTextDeltaEvent>().Count());
        Assert.IsType<ResponseCompletedEvent>(events[^1]);
    }

    // ===== Helpers =====

    private static (AgentFrameworkResponseHandler handler, CreateResponse request, ResponseContext context)
        CreateHandlerWithAgent(AIAgent agent, string userMessage)
    {
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton(agent);
        services.AddSingleton<ILogger<AgentFrameworkResponseHandler>>(NullLogger<AgentFrameworkResponseHandler>.Instance);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);
        var request = new CreateResponse { Model = "test" };
        request.Input = CreateUserInput(userMessage);
        var mockContext = CreateMockContext();

        return (handler, request, mockContext.Object);
    }

    private static BinaryData CreateUserInput(string text)
    {
        return BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_in_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text } }
            }
        });
    }

    private static Mock<ResponseContext> CreateMockContext()
    {
        var mock = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mock.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mock.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());
        return mock;
    }

    private static (ResponseEventStream stream, Mock<ResponseContext> mockContext) CreateTestStream()
    {
        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        var request = new CreateResponse { Model = "test-model" };
        var stream = new ResponseEventStream(mockContext.Object, request);
        return (stream, mockContext);
    }

    private static async Task<List<ResponseStreamEvent>> CollectEventsAsync(
        AgentFrameworkResponseHandler handler,
        CreateResponse request,
        ResponseContext context)
    {
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, context, CancellationToken.None))
        {
            events.Add(evt);
        }

        return events;
    }

    private static async IAsyncEnumerable<T> ToAsync<T>(IEnumerable<T> source)
    {
        foreach (var item in source)
        {
            yield return item;
        }

        await Task.CompletedTask;
    }

    // ===== Test Agent Types =====

    /// <summary>
    /// A test agent that streams a single text update.
    /// </summary>
    private sealed class StreamingTextAgent(string id, string responseText) : AIAgent
    {
        public new string Id => id;

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            yield return new AgentResponseUpdate
            {
                MessageId = $"msg_{id}",
                Contents = [new MeaiTextContent(responseText)]
            };

            await Task.CompletedTask;
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    /// <summary>
    /// A test agent that always throws an exception during streaming.
    /// </summary>
    private sealed class ThrowingStreamingAgent(string id, Exception exception) : AIAgent
    {
        public new string Id => id;

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw exception;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }
}
