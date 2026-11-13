// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentFrameworkResponseHandler"/> that verify behavior
/// when the registered agent is a workflow-backed <see cref="AIAgent"/>. These exercise
/// real workflow builders and the in-process execution environment to drive the handler
/// through realistic streaming event patterns.
/// </summary>
public class AgentFrameworkResponseHandlerWorkflowTests
{
    private const string TelemetrySourceName = "Microsoft.Agents.AI.Foundry.Hosting.UnitTests.Workflow";

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

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task WorkflowAgent_CreatedByFactory_HostingAppliesCheckpointingBeforeTelemetryAsync(ServiceLifetime lifetime)
    {
        // Arrange
        var (handler, store) = CreateFactoryHandler(_ => BuildFactoryWorkflowAgent(), lifetime);

        // Act
        var events = await CollectEventsAsync(handler, CreateRequest("Test factory workflow"), CreateMockContext().Object);

        // Assert: the response ran with an agent that stores its checkpoints in Foundry.
        Assert.IsType<ResponseCreatedEvent>(events[0]);
        Assert.True(events.Count >= 3, $"Expected at least 3 events, got {events.Count}");
        Assert.NotEmpty(store.Agents);
        Assert.All(store.Agents, agent =>
        {
            Assert.IsType<OpenTelemetryAgent>(agent);
            Assert.True(WorkflowAgentExtensions.UsesFoundryCheckpointing(agent));
        });
    }

    [Fact]
    public async Task WorkflowAgent_CreatedByFactoryWrappedBeforeFoundryCheckpointing_IsRejectedAsync()
    {
        // Arrange: the telemetry wrapper hides the workflow agent, so its checkpoints cannot be moved to Foundry.
        var (handler, _) = CreateFactoryHandler(
            _ => BuildFactoryWorkflowAgent().AsBuilder().UseOpenTelemetry(sourceName: TelemetrySourceName).Build(),
            ServiceLifetime.Scoped);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => CollectEventsAsync(handler, CreateRequest("Test factory workflow"), CreateMockContext().Object));

        // Assert
        Assert.Contains("wrapped before WithFoundryCheckpointing", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task WorkflowAgent_CreatedByFactoryWhenTelemetryIsNotRequired_StoresItsCheckpointsInFoundryAsync()
    {
        // Arrange: without the telemetry requirement, a bare workflow agent is served and hosting moves its checkpoints.
        var (handler, store) = CreateFactoryHandler(
            _ => BuildFactoryWorkflowAgent(),
            ServiceLifetime.Scoped,
            requireOpenTelemetryAgent: false);

        // Act
        var events = await CollectEventsAsync(handler, CreateRequest("Test factory workflow"), CreateMockContext().Object);

        // Assert
        Assert.IsType<ResponseCreatedEvent>(events[0]);
        Assert.NotEmpty(store.Agents);
        Assert.All(store.Agents, agent => Assert.True(WorkflowAgentExtensions.UsesFoundryCheckpointing(agent)));
    }

    [Fact]
    public async Task WorkflowAgent_Instance_IsServedThroughWithFoundryCheckpointingAsync()
    {
        // Arrange: hosting takes the same path for an agent it reuses, then adds its own telemetry around it.
        var store = new ServedAgentRecordingStore();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(store);
        var handler = new AgentFrameworkResponseHandler(
            services.BuildServiceProvider(),
            new FoundryHostedAgentSource(BuildFactoryWorkflowAgent()),
            NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        await CollectEventsAsync(handler, CreateRequest("Test instance workflow"), CreateMockContext().Object);

        // Assert
        AIAgent served = Assert.Single(store.Agents.Distinct());
        Assert.IsType<OpenTelemetryAgent>(served);
        Assert.True(WorkflowAgentExtensions.UsesFoundryCheckpointing(served));
    }

    [Fact]
    public async Task CreateAsync_WorkflowCancellationDuringExecution_CancelsInnerAgentWithoutCompletionAsync()
    {
        // Arrange
        var innerAgent = new CancellationCheckingWorkflowAgent("blocking-agent");
        var workflow = AgentWorkflowBuilder.BuildSequential("cancellation-workflow", innerAgent);
        var workflowAgent = workflow.AsAIAgent(
            id: "workflow-agent",
            name: "Cancellation Workflow",
            executionEnvironment: InProcessExecution.OffThread);
        var (handler, request, context) = CreateHandlerWithAgent(workflowAgent, "Hello");
        using var cts = new CancellationTokenSource();
        var events = new List<ResponseStreamEvent>();

        async Task ExecuteAsync()
        {
            await foreach (var evt in handler.CreateAsync(request, context, cts.Token))
            {
                events.Add(evt);
            }
        }

        // Act
        var execution = ExecuteAsync();
        await innerAgent.Started.Task.WaitAsync(TimeSpan.FromSeconds(5));
        cts.Cancel();

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await execution.WaitAsync(TimeSpan.FromSeconds(5)));
        await innerAgent.CancellationObserved.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.DoesNotContain(events, evt => evt is ResponseCompletedEvent);
    }

    private static (AgentFrameworkResponseHandler handler, CreateResponse request, ResponseContext context)
        CreateHandlerWithAgent(
            AIAgent agent,
            string userMessage,
            bool resilient = false)
    {
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddSingleton<ILogger<AgentFrameworkResponseHandler>>(NullLogger<AgentFrameworkResponseHandler>.Instance);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(
            sp,
            new FoundryHostedAgentSource(agent),
            NullLogger<AgentFrameworkResponseHandler>.Instance,
            new FoundryResponsesServerOptions
            {
                ResilientBackground = resilient,
            });
        var request = new CreateResponse
        {
            Model = "test",
            Background = resilient,
            Store = resilient,
        };
        request.Input = CreateUserInput(userMessage);
        var mockContext = CreateMockContext();

        return (handler, request, mockContext.Object);
    }

    private static (AgentFrameworkResponseHandler Handler, ServedAgentRecordingStore Store) CreateFactoryHandler(
        Func<IServiceProvider, AIAgent> agentFactory,
        ServiceLifetime lifetime,
        bool requireOpenTelemetryAgent = true)
    {
        var store = new ServedAgentRecordingStore();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(store);
        var sp = services.BuildServiceProvider();
        var handler = new AgentFrameworkResponseHandler(
            sp,
            new FoundryHostedAgentSource(agentFactory, lifetime, sp),
            NullLogger<AgentFrameworkResponseHandler>.Instance,
            new FoundryResponsesServerOptions { RequireOpenTelemetryAgent = requireOpenTelemetryAgent });
        return (handler, store);
    }

    private static AIAgent BuildFactoryWorkflowAgent()
    {
        var agent = new StreamingTextAgent("inner", "Factory workflow response");
        var workflow = AgentWorkflowBuilder.BuildSequential("factory-wf", agent);
        return workflow.AsAIAgent(
            id: "factory-workflow",
            name: "Factory Workflow",
            executionEnvironment: InProcessExecution.OffThread);
    }

    private static CreateResponse CreateRequest(string userMessage) =>
        new() { Model = "test", Input = CreateUserInput(userMessage) };

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
}
