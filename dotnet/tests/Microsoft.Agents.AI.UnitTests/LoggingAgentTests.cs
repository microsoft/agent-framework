// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="LoggingAgent"/> class.
/// </summary>
public class LoggingAgentTests
{
    [Fact]
    public void Ctor_InvalidArgs_Throws()
    {
        var mockLogger = new Mock<ILogger>();
        Assert.Throws<ArgumentNullException>("innerAgent", () => new LoggingAgent(null!, mockLogger.Object));
        Assert.Throws<ArgumentNullException>("logger", () => new LoggingAgent(new TestAIAgent(), null!));
    }

    [Fact]
    public void Properties_DelegateToInnerAgent()
    {
        // Arrange
        TestAIAgent innerAgent = new()
        {
            NameFunc = () => "TestAgent",
            DescriptionFunc = () => "This is a test agent.",
        };

        var mockLogger = new Mock<ILogger>();
        var agent = new LoggingAgent(innerAgent, mockLogger.Object);

        // Act & Assert
        Assert.Equal("TestAgent", agent.Name);
        Assert.Equal("This is a test agent.", agent.Description);
        Assert.Equal(innerAgent.Id, agent.Id);
    }

    [Fact]
    public void JsonSerializerOptions_Roundtrips()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        var agent = new LoggingAgent(new TestAIAgent(), mockLogger.Object);
        JsonSerializerOptions options = new();

        // Act
        agent.JsonSerializerOptions = options;

        // Assert
        Assert.Same(options, agent.JsonSerializerOptions);
    }

    [Fact]
    public void JsonSerializerOptions_SetNull_Throws()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        var agent = new LoggingAgent(new TestAIAgent(), mockLogger.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => agent.JsonSerializerOptions = null!);
    }

    [Fact]
    public async Task RunAsync_LogsAtDebugLevelAsync()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Debug)).Returns(true);
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Trace)).Returns(false);

        var innerAgent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, thread, options, cancellationToken) =>
            {
                await Task.Yield();
                return new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"));
            }
        };

        var agent = new LoggingAgent(innerAgent, mockLogger.Object);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act
        await agent.RunAsync(messages);

        // Assert
        mockLogger.Verify(
            l => l.Log(
                LogLevel.Debug,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("RunAsync invoked")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);

        mockLogger.Verify(
            l => l.Log(
                LogLevel.Debug,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("RunAsync completed")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsync_LogsAtTraceLevel_IncludesSensitiveDataAsync()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Debug)).Returns(true);
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Trace)).Returns(true);

        var innerAgent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, thread, options, cancellationToken) =>
            {
                await Task.Yield();
                return new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"));
            }
        };

        var agent = new LoggingAgent(innerAgent, mockLogger.Object);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act
        await agent.RunAsync(messages);

        // Assert
        mockLogger.Verify(
            l => l.Log(
                LogLevel.Trace,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("RunAsync invoked")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);

        mockLogger.Verify(
            l => l.Log(
                LogLevel.Trace,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("RunAsync completed")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsync_OnCancellation_LogsCanceledAsync()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Debug)).Returns(true);

        var innerAgent = new TestAIAgent
        {
            RunAsyncFunc = (messages, thread, options, cancellationToken) =>
                throw new OperationCanceledException()
        };

        var agent = new LoggingAgent(innerAgent, mockLogger.Object);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(() => agent.RunAsync(messages));

        mockLogger.Verify(
            l => l.Log(
                LogLevel.Debug,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("canceled")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task RunAsync_OnException_LogsFailedAsync()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Debug)).Returns(true);
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Error)).Returns(true);

        var innerAgent = new TestAIAgent
        {
            RunAsyncFunc = (messages, thread, options, cancellationToken) =>
                throw new InvalidOperationException("Test exception")
        };

        var agent = new LoggingAgent(innerAgent, mockLogger.Object);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(messages));

        mockLogger.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("failed")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task RunStreamingAsync_LogsAtDebugLevelAsync()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Debug)).Returns(true);
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Trace)).Returns(false);

        var innerAgent = new TestAIAgent
        {
            RunStreamingAsyncFunc = CallbackAsync
        };

        static async IAsyncEnumerable<AgentRunResponseUpdate> CallbackAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, "Test");
        }

        var agent = new LoggingAgent(innerAgent, mockLogger.Object);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act
        await foreach (var update in agent.RunStreamingAsync(messages))
        {
            // Consume the stream
        }

        // Assert
        mockLogger.Verify(
            l => l.Log(
                LogLevel.Debug,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("RunStreamingAsync invoked")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);

        mockLogger.Verify(
            l => l.Log(
                LogLevel.Debug,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("RunStreamingAsync completed")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task RunStreamingAsync_LogsUpdatesAtTraceLevelAsync()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Debug)).Returns(true);
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Trace)).Returns(true);

        var innerAgent = new TestAIAgent
        {
            RunStreamingAsyncFunc = CallbackAsync
        };

        static async IAsyncEnumerable<AgentRunResponseUpdate> CallbackAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, "Update 1");
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, "Update 2");
        }

        var agent = new LoggingAgent(innerAgent, mockLogger.Object);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act
        await foreach (var update in agent.RunStreamingAsync(messages))
        {
            // Consume the stream
        }

        // Assert
        mockLogger.Verify(
            l => l.Log(
                LogLevel.Trace,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("received update")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Exactly(2));
    }

    [Fact]
    public async Task RunStreamingAsync_OnCancellation_LogsCanceledAsync()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Debug)).Returns(true);

        var innerAgent = new TestAIAgent
        {
            RunStreamingAsyncFunc = CallbackAsync
        };

        static async IAsyncEnumerable<AgentRunResponseUpdate> CallbackAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();
            throw new OperationCanceledException();
            // The following yield statement is required for async iterator methods but is unreachable.
            // This pattern is intentional for testing exception scenarios in async iterators.
#pragma warning disable CS0162 // Unreachable code detected
            yield break;
#pragma warning restore CS0162 // Unreachable code detected
        }

        var agent = new LoggingAgent(innerAgent, mockLogger.Object);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync(messages))
            {
                // Consume the stream
            }
        });

        mockLogger.Verify(
            l => l.Log(
                LogLevel.Debug,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("canceled")),
                null,
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task RunStreamingAsync_OnException_LogsFailedAsync()
    {
        // Arrange
        var mockLogger = new Mock<ILogger>();
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Debug)).Returns(true);
        mockLogger.Setup(l => l.IsEnabled(LogLevel.Error)).Returns(true);

        var innerAgent = new TestAIAgent
        {
            RunStreamingAsyncFunc = CallbackAsync
        };

        static async IAsyncEnumerable<AgentRunResponseUpdate> CallbackAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();
            throw new InvalidOperationException("Test exception");
            // The following yield statement is required for async iterator methods but is unreachable.
            // This pattern is intentional for testing exception scenarios in async iterators.
#pragma warning disable CS0162 // Unreachable code detected
            yield break;
#pragma warning restore CS0162 // Unreachable code detected
        }

        var agent = new LoggingAgent(innerAgent, mockLogger.Object);
        List<ChatMessage> messages = [new(ChatRole.User, "Hello")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync(messages))
            {
                // Consume the stream
            }
        });

        mockLogger.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("failed")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }
}
