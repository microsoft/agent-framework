// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIAgentExtensions.AsAIFunction"/> method.
/// </summary>
public class AgentExtensionsTests
{
    [Fact]
    public void CreateFromAgent_WithNullAgent_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            AIAgentExtensions.AsAIFunction(null!));

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
        var result = mockAgent.Object.AsAIFunction();

        // Assert
        Assert.NotNull(result);
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
        var result = mockAgent.Object.AsAIFunction();

        // Assert
        Assert.NotNull(result);
        Assert.NotNull(result.Name);
        Assert.Equal("Test description", result.Description);
    }

    [Fact]
    public void CreateFromAgent_WithAgentHavingNullDescription_UsesDefaultDescription()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns((string?)null);

        // Act
        var result = mockAgent.Object.AsAIFunction();

        // Assert
        Assert.NotNull(result);
        Assert.Equal("TestAgent", result.Name);
        Assert.Equal("Invoke an agent to retrieve some information.", result.Description);
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
        var result = mockAgent.Object.AsAIFunction(customOptions);

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
        var result = mockAgent.Object.AsAIFunction(null);

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

        var aiFunction = testAgent.AsAIFunction();

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

        var aiFunction = testAgent.AsAIFunction();

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

        var aiFunction = testAgent.AsAIFunction();

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
        var result = mockAgent.Object.AsAIFunction();

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
        var result = mockAgent.Object.AsAIFunction();

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
        var result = mockAgent.Object.AsAIFunction();

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
        var result = mockAgent.Object.AsAIFunction(customOptions);

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
        var aiFunction = testAgent.AsAIFunction();

        // Act
        var arguments = new AIFunctionArguments() { ["query"] = "Test query" };
        var result = await aiFunction.InvokeAsync(arguments);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("Complex response", result.ToString());
    }

    [Theory]
    [InlineData("MyAgent", "MyAgent")]
    [InlineData("Agent123", "Agent123")]
    [InlineData("Agent_With_Underscores", "Agent_With_Underscores")]
    [InlineData("Agent_With_________@@@@_Underscores", "Agent_With_Underscores")]
    [InlineData("123Agent", "123Agent")]
    [InlineData("My-Agent", "My_Agent")]
    [InlineData("My Agent", "My_Agent")]
    [InlineData("Agent@123", "Agent_123")]
    [InlineData("Agent/With\\Slashes", "Agent_With_Slashes")]
    [InlineData("Agent.With.Dots", "Agent_With_Dots")]
    public void CreateFromAgent_SanitizesAgentName(string agentName, string expectedFunctionName)
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns(agentName);

        // Act
        var result = mockAgent.Object.AsAIFunction();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(expectedFunctionName, result.Name);
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

        public override AgentThread GetNewThread()
            => throw new NotImplementedException();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => throw new NotImplementedException();

        public override string? Name { get; }
        public override string? Description { get; }

        public List<ChatMessage> ReceivedMessages { get; } = [];
        public CancellationToken LastCancellationToken { get; private set; }
        public int RunAsyncCallCount { get; private set; }

        public override Task<AgentRunResponse> RunAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            this.RunAsyncCallCount++;
            this.LastCancellationToken = cancellationToken;
            this.ReceivedMessages.AddRange(messages);

            if (this._exceptionToThrow is not null)
            {
                throw this._exceptionToThrow;
            }

            return Task.FromResult(this._responseToReturn!);
        }

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
            IEnumerable<ChatMessage> messages,
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
