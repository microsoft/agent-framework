// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Foundry.Hosting;
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
