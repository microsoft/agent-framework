// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Covers the readiness check that reports a workflow agent built with a checkpoint manager of its
/// own, whose workflow state would be written somewhere hosting does not manage.
/// </summary>
public class HostedWorkflowCheckpointingHealthCheckTests
{
    [Fact]
    public async Task CheckHealthAsync_WorkflowAgentLeavingStorageToHosting_IsHealthyAsync()
    {
        // Arrange: a workflow agent built the way a hosted container should build one.
        var check = BuildCheckFor(BuildWorkflowAgent(executionEnvironment: null));

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_WorkflowAgentWithItsOwnCheckpointManager_IsUnhealthyAsync()
    {
        // Arrange: the caller named where checkpoints go, so hosting leaves the agent alone and its
        // workflow state never reaches the durable store.
        var environment = InProcessExecution.OffThread.WithCheckpointing(CheckpointManager.CreateInMemory());
        var check = BuildCheckFor(BuildWorkflowAgent(environment));

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        var reported = Assert.IsType<List<string>>(result.Data["incompatibleAgents"]);
        Assert.Equal(["WorkflowAgent"], reported);
    }

    [Fact]
    public async Task CheckHealthAsync_WorkflowAgentBehindAWrapper_IsStillReportedAsync()
    {
        // Arrange: middleware around the agent must not hide the misconfiguration.
        var environment = InProcessExecution.OffThread.WithCheckpointing(CheckpointManager.CreateInMemory());
        var check = BuildCheckFor(new PassThroughAgent(BuildWorkflowAgent(environment)));

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_WrappedWorkflowWithoutOwnManager_IsUnhealthyAsync()
    {
        // Arrange: the metadata flows through the wrapper, but hosting cannot replace the inner
        // workflow agent without discarding that wrapper.
        var check = BuildCheckFor(new PassThroughAgent(BuildWorkflowAgent(executionEnvironment: null)));

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.Equal(["WorkflowAgent"], Assert.IsType<List<string>>(result.Data["incompatibleAgents"]));
    }

    [Fact]
    public async Task CheckHealthAsync_AgentThatDoesNotRunAWorkflow_IsPassedOverAsync()
    {
        // Arrange: an agent with no checkpoints at all has nothing to misconfigure.
        var check = BuildCheckFor(new ChatClientAgent(NewSilentChatClient(), new ChatClientAgentOptions { Name = "plain" }));

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_NotInAFoundryContainer_IsHealthyAsync()
    {
        // Arrange: outside a Foundry container nothing redirects checkpoints, so an agent bringing
        // its own manager is not competing with anything.
        var environment = InProcessExecution.OffThread.WithCheckpointing(CheckpointManager.CreateInMemory());
        var check = BuildCheckFor(BuildWorkflowAgent(environment));
        check.IsHosted = false;

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_WorkflowAgentCheckpointedInFoundryBeforeWrapping_IsHealthyAsync()
    {
        // Arrange: the factory moved the checkpoints to Foundry, then added middleware, as hosting does.
        AIAgent checkpointed = BuildWorkflowAgent(executionEnvironment: null)
            .WithFoundryCheckpointing(new ServiceCollection().BuildServiceProvider());
        using var telemetry = new OpenTelemetryAgent(checkpointed, "Microsoft.Agents.AI.Foundry.Hosting.UnitTests.Readiness");
        var check = BuildCheckFor(new PassThroughAgent(telemetry));

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_ScopedWorkflowAgentFactory_IsCreatedFromAScopeAsync()
    {
        // Arrange: the factory resolves a scoped dependency, which fails from the root container when scopes
        // are validated.
        var environment = InProcessExecution.OffThread.WithCheckpointing(CheckpointManager.CreateInMemory());
        var services = new ServiceCollection();
        services.AddScoped(_ => new ScopedDependency());
        var provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        var agentSource = new FoundryHostedAgentSource(
            sp =>
            {
                _ = sp.GetRequiredService<ScopedDependency>();
                return BuildWorkflowAgent(environment);
            },
            ServiceLifetime.Scoped,
            provider,
            requireOpenTelemetryAgent: false);
        var check = new HostedWorkflowCheckpointingHealthCheck(provider, agentSource)
        {
            IsHosted = true,
        };

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert: the agent was resolved and inspected rather than failing the readiness probe.
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.Equal(["WorkflowAgent"], Assert.IsType<List<string>>(result.Data["incompatibleAgents"]));
    }

    private static HostedWorkflowCheckpointingHealthCheck BuildCheckFor(AIAgent agent)
        => new(new ServiceCollection().BuildServiceProvider(), new FoundryHostedAgentSource(agent))
        {
            IsHosted = true,
        };

    private sealed class ScopedDependency;

    private static AIAgent BuildWorkflowAgent(InProcessExecutionEnvironment? executionEnvironment)
    {
        var inner = new ChatClientAgent(NewSilentChatClient(), new ChatClientAgentOptions { Name = "inner" });
        var workflow = new ConcurrentWorkflowBuilder(inner).WithOutputFrom(inner).Build();

        return workflow.AsAIAgent(
            id: "workflow-agent",
            name: "WorkflowAgent",
            executionEnvironment: executionEnvironment);
    }

    private static HealthCheckContext NewContext() => new()
    {
        Registration = new HealthCheckRegistration(
            "foundry-workflow-checkpointing",
            _ => new Mock<IHealthCheck>().Object,
            HealthStatus.Unhealthy,
            tags: null),
    };

    private static IChatClient NewSilentChatClient()
    {
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "ok")));
        return client.Object;
    }

    private sealed class PassThroughAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent);
}
