// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Declarative.UnitTests;

/// <summary>
/// Unit tests for <see cref="AggregatorAgentFactory"/>
/// </summary>
public sealed class AggregatorAgentFactoryTests
{
    [Fact]
    public void AggregatorAgentFactory_ThrowsForEmptyArray()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() => new AggregatorAgentFactory([]));
    }

    [Fact]
    public async Task AggregatorAgentFactory_ReturnsNull()
    {
        // Arrange
        var factory = new AggregatorAgentFactory([new TestAgentFactory(null)]);

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
        var factory = new AggregatorAgentFactory([new TestAgentFactory(null), new TestAgentFactory(agentToReturn)]);

        // Act
        var agent = await factory.TryCreateAsync(new GptComponentMetadata("test"));

        // Assert
        Assert.Equal(agentToReturn, agent);
    }

    private sealed class TestAgentFactory : AgentFactory
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
        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            throw new NotImplementedException();
        }

        public override AgentThread GetNewThread()
        {
            throw new NotImplementedException();
        }

        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }
    }
}
