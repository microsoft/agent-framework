// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentAIFunctionFactory"/> class.
/// </summary>
public class AgentAIFunctionFactoryTests
{
    [Fact]
    public void CreateFromAgent_WithNullAgent_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            AgentAIFunctionFactory.CreateFromAgent(null!));

        Assert.Equal("agent", exception.ParamName);
    }

    [Fact]
    public void CreateFromAgent_WithValidAgent_ReturnsAIFunction()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns("Test agent description");

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object);

        // Assert
        Assert.NotNull(result);
        Assert.True(result is AIFunction);
        Assert.Equal("TestAgent", result.Name);
        Assert.Equal("Test agent description", result.Description);
    }

    [Fact]
    public void CreateFromAgent_WithAgentHavingNullName_UsesDefaultName()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns((string?)null);
        mockAgent.Setup(a => a.Description).Returns("Test description");

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object);

        // Assert
        Assert.NotNull(result);
        Assert.NotNull(result.Name);
        Assert.Equal("Test description", result.Description);
    }

    [Fact]
    public void CreateFromAgent_WithAgentHavingNullDescription_UsesEmptyDescription()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns((string?)null);

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("TestAgent", result.Name);
        Assert.Equal(string.Empty, result.Description);
    }

    [Fact]
    public void CreateFromAgent_WithCustomOptions_UsesCustomOptions()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns("Test agent description");

        var customOptions = new AIFunctionFactoryOptions
        {
            Name = "CustomName",
            Description = "Custom description"
        };

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object, customOptions);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("CustomName", result.Name);
        Assert.Equal("Custom description", result.Description);
    }

    [Fact]
    public void CreateFromAgent_WithNullOptions_UsesAgentProperties()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns("Test agent description");

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object, null);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("TestAgent", result.Name);
        Assert.Equal("Test agent description", result.Description);
    }

    [Fact]
    public async Task CreateFromAgent_WhenFunctionInvokedAsync_CallsAgentRunAsync()
    {
        // Arrange
        var expectedResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"));
        var testAgent = new TestAgent("TestAgent", "Test description", expectedResponse);

        var aiFunction = AgentAIFunctionFactory.CreateFromAgent(testAgent);

        // Act
        var arguments = new AIFunctionArguments() { ["query"] = "Test query" };
        var result = await aiFunction.InvokeAsync(arguments);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("Test response", result.ToString());
    }

    [Fact]
    public async Task CreateFromAgent_WhenFunctionInvokedWithCancellationTokenAsync_PassesCancellationTokenAsync()
    {
        // Arrange
        var expectedResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"));
        var testAgent = new TestAgent("TestAgent", "Test description", expectedResponse);
        using var cancellationTokenSource = new CancellationTokenSource();
        var cancellationToken = cancellationTokenSource.Token;

        var aiFunction = AgentAIFunctionFactory.CreateFromAgent(testAgent);

        // Act
        var arguments = new AIFunctionArguments() { ["query"] = "Test query" };
        var result = await aiFunction.InvokeAsync(arguments, cancellationToken);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("Test response", result.ToString());
    }

    [Fact]
    public async Task CreateFromAgent_WhenAgentThrowsExceptionAsync_PropagatesExceptionAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Test exception");
        var testAgent = new TestAgent("TestAgent", "Test description", expectedException);

        var aiFunction = AgentAIFunctionFactory.CreateFromAgent(testAgent);

        // Act & Assert
        var arguments = new AIFunctionArguments() { ["query"] = "Test query" };
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await aiFunction.InvokeAsync(arguments));

        Assert.Same(expectedException, actualException);
    }

    [Fact]
    public void CreateFromAgent_ReturnsInvokableFunction()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns("Test description");

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object);

        // Assert
        Assert.NotNull(result);

        // Verify the function has the expected parameter schema
        var parameters = result.JsonSchema;

        // Verify it has a query parameter
        Assert.True(parameters.TryGetProperty("properties", out var properties));
        Assert.True(properties.TryGetProperty("query", out var queryProperty));
        Assert.True(queryProperty.TryGetProperty("type", out var typeProperty));
        Assert.Equal("string", typeProperty.GetString());
    }

    [Fact]
    public void CreateFromAgent_WithEmptyAgentName_CreatesValidFunction()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns(string.Empty);
        mockAgent.Setup(a => a.Description).Returns("Test description");

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(string.Empty, result.Name);
        Assert.Equal("Test description", result.Description);
    }

    [Fact]
    public void CreateFromAgent_WithEmptyAgentDescription_CreatesValidFunction()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns(string.Empty);

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("TestAgent", result.Name);
        Assert.Equal(string.Empty, result.Description);
    }

    [Fact]
    public void CreateFromAgent_WithCustomOptionsOverridingNullAgentProperties_UsesCustomOptions()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns((string?)null);
        mockAgent.Setup(a => a.Description).Returns((string?)null);

        var customOptions = new AIFunctionFactoryOptions
        {
            Name = "OverrideName",
            Description = "Override description"
        };

        // Act
        var result = AgentAIFunctionFactory.CreateFromAgent(mockAgent.Object, customOptions);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("OverrideName", result.Name);
        Assert.Equal("Override description", result.Description);
    }

    [Fact]
    public async Task CreateFromAgent_InvokeWithComplexResponseFromAgentAsync_ReturnsCorrectResponseAsync()
    {
        // Arrange
        var expectedResponse = new AgentRunResponse
        {
            AgentId = "agent-123",
            ResponseId = "response-456",
            CreatedAt = DateTimeOffset.UtcNow,
            Messages = { new ChatMessage(ChatRole.Assistant, "Complex response") }
        };

        var testAgent = new TestAgent("TestAgent", "Test description", expectedResponse);
        var aiFunction = AgentAIFunctionFactory.CreateFromAgent(testAgent);

        // Act
        var arguments = new AIFunctionArguments() { ["query"] = "Test query" };
        var result = await aiFunction.InvokeAsync(arguments);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("Complex response", result.ToString());
    }

    /// <summary>
    /// Test implementation of AIAgent for testing purposes.
    /// </summary>
    private sealed class TestAgent : AIAgent
    {
        private readonly AgentRunResponse? _responseToReturn;
        private readonly Exception? _exceptionToThrow;

        public TestAgent(string? name, string? description, AgentRunResponse responseToReturn)
        {
            this.Name = name;
            this.Description = description;
            this._responseToReturn = responseToReturn;
        }

        public TestAgent(string? name, string? description, Exception exceptionToThrow)
        {
            this.Name = name;
            this.Description = description;
            this._exceptionToThrow = exceptionToThrow;
        }

        public override string? Name { get; }
        public override string? Description { get; }

        public List<ChatMessage> ReceivedMessages { get; } = new();
        public CancellationToken LastCancellationToken { get; private set; }
        public int RunAsyncCallCount { get; private set; }

        public override Task<AgentRunResponse> RunAsync(
            IReadOnlyCollection<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            this.RunAsyncCallCount++;
            this.LastCancellationToken = cancellationToken;
            this.ReceivedMessages.AddRange(messages);

            if (this._exceptionToThrow != null)
            {
                throw this._exceptionToThrow;
            }

            return Task.FromResult(this._responseToReturn!);
        }

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
            IReadOnlyCollection<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var response = await this.RunAsync(messages, thread, options, cancellationToken);
            foreach (var update in response.ToAgentRunResponseUpdates())
            {
                yield return update;
            }
        }
    }
}
