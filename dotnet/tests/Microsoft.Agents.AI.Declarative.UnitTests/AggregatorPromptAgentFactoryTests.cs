// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Declarative.UnitTests;

/// <summary>
/// Unit tests for <see cref="AggregatorPromptAgentFactory"/>
/// </summary>
public sealed class AggregatorPromptAgentFactoryTests
{
    [Fact]
    public void AggregatorAgentFactory_ThrowsForEmptyArray()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() => new AggregatorPromptAgentFactory([]));
    }

    [Fact]
    public async Task AggregatorAgentFactory_ReturnsNull()
    {
        // Arrange
        var factory = new AggregatorPromptAgentFactory([new TestAgentFactory(null)]);

        // Act
        var agent = await factory.TryCreateAsync(new GptComponentMetadata("test"));

        // Assert
        Assert.Null(agent);
    }

    [Fact]
    public async Task AggregatorAgentFactory_ReturnsAgent()
    {
        // Arrange
        var agentToReturn = new TestAgent();
        var factory = new AggregatorPromptAgentFactory([new TestAgentFactory(null), new TestAgentFactory(agentToReturn)]);

        // Act
        var agent = await factory.TryCreateAsync(new GptComponentMetadata("test"));

        // Assert
        Assert.Equal(agentToReturn, agent);
    }

    private sealed class TestAgentFactory : PromptAgentFactory
    {
        private readonly AIAgent? _agentToReturn;

        public TestAgentFactory(AIAgent? agentToReturn = null)
        {
            this._agentToReturn = agentToReturn;
        }

        public override Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
        {
            return Task.FromResult(this._agentToReturn);
        }
    }

    private sealed class TestAgent : AIAgent
    {
        public override ValueTask<AgentSession> DeserializeSessionAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public override JsonElement SerializeSession(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            throw new NotImplementedException();
        }

        public override ValueTask<AgentSession> CreateSessionAsync(CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }
    }
}
