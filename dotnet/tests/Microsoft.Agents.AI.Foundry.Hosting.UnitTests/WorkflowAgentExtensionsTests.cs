// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Covers <see cref="WorkflowAgentExtensions.WithFoundryCheckpointing"/>, which hosting uses for the agent it
/// serves and a factory uses before wrapping a workflow agent itself.
/// </summary>
public sealed class WorkflowAgentExtensionsTests
{
    private const string TelemetrySourceName = "Microsoft.Agents.AI.Foundry.Hosting.UnitTests.Checkpointing";

    private static readonly IServiceProvider s_services = new ServiceCollection().BuildServiceProvider();

    [Fact]
    public void WithFoundryCheckpointing_WorkflowAgent_ReturnsACopyThatStoresItsCheckpointsInFoundry()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);

        // Act
        AIAgent copy = agent.WithFoundryCheckpointing(s_services);

        // Assert: outside Foundry the copy uses the AgentServer SDK's local state-store fallback.
        Assert.NotSame(agent, copy);
        Assert.True(copy.GetService<WorkflowAgentMetadata>()?.UsesOwnCheckpointStorage);
        Assert.True(WorkflowAgentExtensions.UsesFoundryCheckpointing(copy));
        Assert.False(WorkflowAgentExtensions.UsesFoundryCheckpointing(agent));
    }

    [Fact]
    public void WithFoundryCheckpointing_CalledAgain_ReturnsTheSameCopy()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);
        AIAgent copy = agent.WithFoundryCheckpointing(s_services);

        // Act & Assert: on the original agent and on the copy alike.
        Assert.Same(copy, agent.WithFoundryCheckpointing(s_services));
        Assert.Same(copy, copy.WithFoundryCheckpointing(s_services));
    }

    [Fact]
    public void WithFoundryCheckpointing_CopyBehindATelemetryWrapper_IsStillRecognized()
    {
        // Arrange
        AIAgent copy = BuildWorkflowAgent(executionEnvironment: null).WithFoundryCheckpointing(s_services);
        using var wrapped = new OpenTelemetryAgent(copy, TelemetrySourceName);

        // Act
        AIAgent result = wrapped.WithFoundryCheckpointing(s_services);

        // Assert
        Assert.Same(wrapped, result);
        Assert.True(WorkflowAgentExtensions.UsesFoundryCheckpointing(wrapped));
    }

    [Fact]
    public void WithFoundryCheckpointing_WorkflowAgentAlreadyWrapped_IsReturnedUnchanged()
    {
        // Arrange: only the workflow agent itself can be copied.
        using var wrapped = new OpenTelemetryAgent(BuildWorkflowAgent(executionEnvironment: null), TelemetrySourceName);

        // Act
        AIAgent result = wrapped.WithFoundryCheckpointing(s_services);

        // Assert
        Assert.Same(wrapped, result);
        Assert.False(WorkflowAgentExtensions.UsesFoundryCheckpointing(result));
    }

    [Fact]
    public void WithFoundryCheckpointing_WorkflowAgentWithItsOwnCheckpointManager_IsReturnedUnchanged()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(InProcessExecution.OffThread.WithCheckpointing(CheckpointManager.CreateInMemory()));

        // Act
        AIAgent result = agent.WithFoundryCheckpointing(s_services);

        // Assert: the caller chose where checkpoints go, and that choice is kept.
        Assert.Same(agent, result);
        Assert.False(WorkflowAgentExtensions.UsesFoundryCheckpointing(result));
    }

    [Fact]
    public void WithFoundryCheckpointing_AgentThatDoesNotRunAWorkflow_IsReturnedUnchanged()
    {
        // Arrange
        var agent = new ChatClientAgent(NewSilentChatClient(), new ChatClientAgentOptions { Name = "plain" });

        // Act
        AIAgent result = agent.WithFoundryCheckpointing(s_services);

        // Assert
        Assert.Same(agent, result);
        Assert.False(WorkflowAgentExtensions.UsesFoundryCheckpointing(result));
    }

    [Fact]
    public void WithFoundryCheckpointing_NullArguments_Throw()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ((AIAgent)null!).WithFoundryCheckpointing(s_services));
        Assert.Throws<ArgumentNullException>(() => agent.WithFoundryCheckpointing(null!));
    }

    private static AIAgent BuildWorkflowAgent(InProcessExecutionEnvironment? executionEnvironment)
    {
        var inner = new ChatClientAgent(NewSilentChatClient(), new ChatClientAgentOptions { Name = "inner" });
        var workflow = new ConcurrentWorkflowBuilder(inner).WithOutputFrom(inner).Build();

        return workflow.AsAIAgent(
            id: "workflow-agent",
            name: "WorkflowAgent",
            executionEnvironment: executionEnvironment);
    }

    private static IChatClient NewSilentChatClient()
    {
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "ok")));
        return client.Object;
    }
}
