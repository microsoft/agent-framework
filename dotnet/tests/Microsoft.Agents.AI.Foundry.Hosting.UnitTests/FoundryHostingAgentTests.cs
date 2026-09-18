// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class FoundryHostingAgentTests
{
    [Fact]
    public void ResolveSessionStorageIdentity_KeyedAliasOfDefaultAgent_UsesDefaultIdentity()
    {
        // Arrange
        var agent = new TestAgent("billing");

        // Act
        string identity = FoundryHostingAgent.ResolveSessionStorageIdentity(
            agent,
            registrationKey: "billing",
            defaultAgent: agent);

        // Assert
        Assert.Equal("name:billing", identity);
    }

    [Fact]
    public void ResolveSessionStorageIdentity_IndependentKeyedAgent_UsesRegistrationKey()
    {
        // Arrange
        var agent = new TestAgent("shared-name");
        var defaultAgent = new TestAgent("shared-name");

        // Act
        string identity = FoundryHostingAgent.ResolveSessionStorageIdentity(
            agent,
            registrationKey: "billing",
            defaultAgent);

        // Assert
        Assert.Equal("key:billing", identity);
    }

    [Fact]
    public void ResolveSessionStorageIdentity_UnnamedDefaultAgent_UsesDefaultIdentity()
    {
        // Arrange
        var agent = new TestAgent();

        // Act
        string identity = FoundryHostingAgent.ResolveSessionStorageIdentity(
            agent,
            registrationKey: null,
            defaultAgent: agent);

        // Assert
        Assert.Equal("default", identity);
    }

    [Fact]
    public void GetService_ThroughOuterMiddleware_ReturnsHostingAgent()
    {
        // Arrange
        var hostingAgent = new FoundryHostingAgent(new TestAgent("billing"), "name:billing");
        AIAgent outerAgent = FoundryHostingExtensions.ApplyOpenTelemetry(hostingAgent);

        // Act
        var resolved = outerAgent.GetService<FoundryHostingAgent>();

        // Assert
        Assert.Same(hostingAgent, resolved);
        Assert.Equal("name:billing", resolved!.SessionStorageIdentity);
    }

    private sealed class TestAgent(string? name = null) : AIAgent
    {
        public override string? Name => name;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }
}
