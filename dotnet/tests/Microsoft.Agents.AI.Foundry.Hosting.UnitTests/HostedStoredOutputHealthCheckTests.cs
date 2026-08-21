// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using Moq;
using CreateResponseOptions = OpenAI.Responses.CreateResponseOptions;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Covers the readiness check that reports an agent configured to have its own service store the
/// responses it produces, so a container recording the conversation twice never takes traffic.
/// </summary>
public class HostedStoredOutputHealthCheckTests
{
    [Fact]
    public async Task CheckHealthAsync_AgentThatAsksNotToStore_IsHealthyAsync()
    {
        // Arrange: an agent built the way a hosted container should build one.
        var agent = new ChatClientAgent(
            NewSilentChatClient(),
            new ChatClientAgentOptions
            {
                Name = "asks-not-to-store",
                ChatOptions = new ChatOptions
                {
                    RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = false },
                },
            });

        var check = BuildCheckFor(agent);

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_AgentThatAsksToStore_IsUnhealthyAsync()
    {
        // Arrange: an agent that asks its own service to keep the responses it produces, which is a
        // second recording of a conversation the hosting service already keeps.
        var agent = new ChatClientAgent(
            NewSilentChatClient(),
            new ChatClientAgentOptions
            {
                Name = "asks-to-store",
                ChatOptions = new ChatOptions
                {
                    RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = true },
                },
            });

        var check = BuildCheckFor(agent);

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert: the deployment is reported, and the agent named, before it can take traffic.
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.Contains("asks-to-store", (List<string>)result.Data["storingAgents"]);
    }

    [Fact]
    public async Task CheckHealthAsync_StoringIsAllowed_SkipsTheCheckAsync()
    {
        // Arrange: the same agent, in a container that opted into keeping its own recording.
        var agent = new ChatClientAgent(
            NewSilentChatClient(),
            new ChatClientAgentOptions
            {
                Name = "asks-to-store",
                ChatOptions = new ChatOptions
                {
                    RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = true },
                },
            });

        var check = BuildCheckFor(agent, new FoundryResponsesOptions { AllowStoredOutputEnabled = true });

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert: the container's own choice is not second-guessed.
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_AgentWithNoSettingOfItsOwn_IsHealthyAsync()
    {
        // Arrange: an agent that builds no request of its own, so there is nothing to read. Hosting
        // turns storing off per run anyway, and an unknown is not worth an outage.
        var check = BuildCheckFor(new ChatClientAgent(NewSilentChatClient(), new ChatClientAgentOptions { Name = "says-nothing" }));

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_AgentThatIsNotAChatClientAgent_IsHealthyAsync()
    {
        // Arrange: hosting only reaches the setting through a ChatClientAgent's chat options, so any
        // other agent runs untouched and there is nothing to report about it.
        var agent = new Mock<AIAgent>();
        agent.Setup(a => a.GetService(It.IsAny<Type>(), It.IsAny<object?>())).Returns(null!);

        var check = BuildCheckFor(agent.Object);

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_AgentWithProviders_LeavesThemUntouchedAsync()
    {
        // Arrange: a context provider and a chat history provider are the parts most likely to call
        // outside the container and to write state, so a readiness probe must not set them running.
        var contextProvider = new RecordingContextProvider();
        var historyProvider = new RecordingChatHistoryProvider();
        var agent = new ChatClientAgent(
            NewSilentChatClient(),
            new ChatClientAgentOptions
            {
                Name = "has-providers",
                ChatHistoryProvider = historyProvider,
                AIContextProviders = [contextProvider],
                ChatOptions = new ChatOptions
                {
                    RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = true },
                },
            });

        var check = BuildCheckFor(agent);

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert: the setting is still read, and neither provider was asked to do anything.
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.False(contextProvider.WasInvoked);
        Assert.False(historyProvider.WasInvoked);
    }

    [Fact]
    public async Task CheckHealthAsync_WrappedChatClientAgent_IsHealthyWithoutRunningItAsync()
    {
        // Arrange: rebuilding only the leaf would miss any option changes made by this wrapper.
        var inner = new ChatClientAgent(
            NewSilentChatClient(),
            new ChatClientAgentOptions { Name = "wrapped" });
        AIAgent wrapper = new PassThroughAgent(inner);
        var check = BuildCheckFor(wrapper);

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_FoundryAgent_IsProbeableAsync()
    {
        // Arrange: FoundryAgent is a transparent wrapper around its ChatClientAgent.
        var inner = new ChatClientAgent(
            NewSilentChatClient(),
            new ChatClientAgentOptions
            {
                Name = "foundry-agent",
                ChatOptions = new ChatOptions
                {
                    RawRepresentationFactory = _ => new CreateResponseOptions { StoredOutputEnabled = true },
                },
            });
        var check = BuildCheckFor(new FoundryAgent(inner));

        // Act
        var result = await check.CheckHealthAsync(NewContext(), CancellationToken.None);

        // Assert
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.Contains("foundry-agent", (List<string>)result.Data["storingAgents"]);
    }

    private static HostedStoredOutputHealthCheck BuildCheckFor(AIAgent agent, FoundryResponsesOptions? hostingOptions = null)
    {
        var services = new ServiceCollection();
        services.AddSingleton(agent);
        return new HostedStoredOutputHealthCheck(
            services.BuildServiceProvider(),
            Options.Create(hostingOptions ?? new FoundryResponsesOptions()));
    }

    private static HealthCheckContext NewContext() => new()
    {
        Registration = new HealthCheckRegistration(
            "foundry-stored-output",
            _ => new Mock<IHealthCheck>().Object,
            HealthStatus.Unhealthy,
            tags: null),
    };

    /// <summary>A chat client that answers without calling anything and keeps no conversation.</summary>
    private static IChatClient NewSilentChatClient()
    {
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(() => OneUpdateAsync());
        client.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "ok")));
        return client.Object;
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> OneUpdateAsync()
    {
        await Task.CompletedTask;
        yield return new ChatResponseUpdate(ChatRole.Assistant, "ok");
    }

    /// <summary>Records whether the agent ever set it running. Stands in for a memory or search provider.</summary>
    private sealed class RecordingContextProvider : AIContextProvider
    {
        public bool WasInvoked { get; private set; }

        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            this.WasInvoked = true;
            return new(new AIContext());
        }

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.WasInvoked = true;
            return default;
        }
    }

    /// <summary>Records whether the agent ever set it running. Stands in for a database-backed history store.</summary>
    private sealed class RecordingChatHistoryProvider : ChatHistoryProvider
    {
        public bool WasInvoked { get; private set; }

        protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            this.WasInvoked = true;
            return new([]);
        }

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.WasInvoked = true;
            return default;
        }
    }

    private sealed class PassThroughAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent);
}
