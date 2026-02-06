// Copyright (c) Microsoft. All rights reserved.

using Microsoft.DurableTask;
using Moq;

namespace Microsoft.Agents.AI.DurableTask.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DurableAIAgent"/> class.
/// </summary>
public sealed class DurableAIAgentTests
{
    private readonly Mock<TaskOrchestrationContext> _mockContext;
    private readonly DurableAIAgent _agent;

    public DurableAIAgentTests()
    {
        this._mockContext = new Mock<TaskOrchestrationContext>(MockBehavior.Strict);
        this._agent = new DurableAIAgent(this._mockContext.Object, "test-agent");
    }

    /// <summary>
    /// Verify that GetService returns the agent for matching types and null for non-matching types.
    /// </summary>
    [Fact]
    public void GetService_ReturnsCorrectResults()
    {
        // Act & Assert - returns agent for matching types
        Assert.Same(this._agent, this._agent.GetService(typeof(DurableAIAgent)));
        Assert.Same(this._agent, this._agent.GetService(typeof(AIAgent)));
        Assert.Same(this._agent, this._agent.GetService<DurableAIAgent>());

        // Act & Assert - returns metadata
        Assert.IsType<AIAgentMetadata>(this._agent.GetService(typeof(AIAgentMetadata)));

        // Act & Assert - returns null for unrelated types and keyed requests
        Assert.Null(this._agent.GetService(typeof(string)));
        Assert.Null(this._agent.GetService<string>());
        Assert.Null(this._agent.GetService(typeof(DurableAIAgent), "some-key"));

        // Act & Assert - throws for null
        Assert.Throws<ArgumentNullException>(() => this._agent.GetService(null!));
    }

    /// <summary>
    /// Verify that DurableAIAgent supports structured output and has correct provider name.
    /// </summary>
    [Fact]
    public void Metadata_HasCorrectProviderNameAndSupportsStructuredOutput()
    {
        // Arrange
        AIAgentMetadata? metadata = this._agent.GetService<AIAgentMetadata>();

        // Assert - metadata indicates structured output support
        Assert.NotNull(metadata);
        Assert.True(metadata!.SupportsStructuredOutput);
        Assert.Equal("durable-task", metadata.ProviderName);
    }

    /// <summary>
    /// Verify that Name property returns the agent name provided during creation.
    /// </summary>
    [Fact]
    public void Name_ReturnsAgentNameProvidedDuringCreation()
    {
        // Assert
        Assert.Equal("test-agent", this._agent.Name);
    }
}
