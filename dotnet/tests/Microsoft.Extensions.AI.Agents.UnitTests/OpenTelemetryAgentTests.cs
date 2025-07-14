// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Moq;
using OpenTelemetry.Trace;

namespace Microsoft.Extensions.AI.Agents.UnitTests;

public class OpenTelemetryAgentTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunAsync_ExpectedTelemetryData_CollectedAsync(bool withError)
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using ILoggerFactory loggerFactory = LoggerFactory.Create(b => { });

        var mockAgent = CreateMockAgent(withError);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, loggerFactory.CreateLogger("test"), sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "What's the weather like?")
        };

        var thread = new Mock<AgentThread>().Object;

        // Act & Assert
        if (withError)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(
                () => telemetryAgent.RunAsync(messages, thread));
            Assert.Equal("Test error", exception.Message);
        }
        else
        {
            var response = await telemetryAgent.RunAsync(messages, thread);
            Assert.NotNull(response);
            Assert.Equal("Test response", response.Messages.First().Text);
        }

        // Verify activity was created
        var activity = Assert.Single(activities);
        Assert.NotNull(activity.Id);
        Assert.NotEmpty(activity.Id);
        Assert.Equal($"{AgentOpenTelemetryConsts.Agent.Run} TestAgent", activity.DisplayName);
        Assert.Equal(ActivityKind.Client, activity.Kind);

        // Verify activity tags
        Assert.Equal(AgentOpenTelemetryConsts.Agent.Run, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Operation.Name));
        Assert.Equal("test-agent-id", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Request.Id));
        Assert.Equal("TestAgent", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Request.Name));
        Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Request.MessageCount));

        if (withError)
        {
            Assert.Equal("System.InvalidOperationException", activity.GetTagItem(AgentOpenTelemetryConsts.ErrorInfo.Type));
            Assert.Equal(ActivityStatusCode.Error, activity.Status);
            Assert.Equal("Test error", activity.StatusDescription);
        }
        else
        {
            Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Response.MessageCount));
            Assert.Equal("test-response-id", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Response.Id));
            Assert.Equal(10, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Usage.InputTokens));
            Assert.Equal(20, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Usage.OutputTokens));
        }

        Assert.True(activity.Duration.TotalMilliseconds > 0);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunStreamingAsync_ExpectedTelemetryData_CollectedAsync(bool withError)
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using ILoggerFactory loggerFactory = LoggerFactory.Create(b => { });

        var mockAgent = CreateMockStreamingAgent(withError);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, loggerFactory.CreateLogger("test"), sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Tell me a story")
        };

        var thread = new Mock<AgentThread>().Object;

        // Act & Assert
        if (withError)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            {
                await foreach (var update in telemetryAgent.RunStreamingAsync(messages, thread))
                {
                    // Should not reach here
                }
            });
            Assert.Equal("Streaming error", exception.Message);
        }
        else
        {
            var updates = new List<AgentRunResponseUpdate>();
            await foreach (var update in telemetryAgent.RunStreamingAsync(messages, thread))
            {
                updates.Add(update);
            }
            Assert.NotEmpty(updates);
        }

        // Verify activity was created
        var activity = Assert.Single(activities);
        Assert.NotNull(activity.Id);
        Assert.NotEmpty(activity.Id);
        Assert.Equal($"{AgentOpenTelemetryConsts.Agent.RunStreaming} TestAgent", activity.DisplayName);
        Assert.Equal(ActivityKind.Client, activity.Kind);

        // Verify activity tags
        Assert.Equal(AgentOpenTelemetryConsts.Agent.RunStreaming, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Operation.Name));
        Assert.Equal("test-agent-id", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Request.Id));
        Assert.Equal("TestAgent", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Request.Name));
        Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Request.MessageCount));

        if (withError)
        {
            Assert.Equal("System.InvalidOperationException", activity.GetTagItem(AgentOpenTelemetryConsts.ErrorInfo.Type));
            Assert.Equal(ActivityStatusCode.Error, activity.Status);
            Assert.Equal("Streaming error", activity.StatusDescription);
        }
        else
        {
            Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Response.MessageCount));
            Assert.Equal("stream-response-id", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Response.Id));
            Assert.Equal(15, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Usage.InputTokens));
            Assert.Equal(25, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Usage.OutputTokens));
        }

        Assert.True(activity.Duration.TotalMilliseconds > 0);
    }

    [Fact]
    public async Task RunAsync_WithChatClientAgent_IncludesInstructionsAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response")));

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Id = "chat-agent-id",
            Name = "ChatAgent",
            Instructions = "You are a helpful assistant."
        });

        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);
        Assert.Equal("You are a helpful assistant.", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Request.Instructions));
    }

    [Fact]
    public async Task RunAsync_WithThreadId_IncludesThreadIdAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockAgent = CreateMockAgent(false);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        var thread = new AgentThread { Id = "thread-123" };

        // Act
        await telemetryAgent.RunAsync(messages, thread);

        // Assert
        var activity = Assert.Single(activities);
        Assert.Equal("thread-123", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Request.ThreadId));
    }

    [Fact]
    public void WithOpenTelemetry_ExtensionMethod_CreatesOpenTelemetryAgent()
    {
        // Arrange
        var mockAgent = new Mock<Agent>();
        mockAgent.Setup(a => a.Id).Returns("test-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");

        // Act
        using var telemetryAgent = mockAgent.Object.WithOpenTelemetry();

        // Assert
        Assert.IsType<OpenTelemetryAgent>(telemetryAgent);
        Assert.Equal("test-id", telemetryAgent.Id);
        Assert.Equal("TestAgent", telemetryAgent.Name);
    }

    [Fact]
    public async Task RunAsync_NoListeners_NoActivitiesCreatedAsync()
    {
        // Arrange - No tracer provider, so no listeners
        var mockAgent = CreateMockAgent(false);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: "test-source");

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert - Should complete without creating activities
        mockAgent.Verify(a => a.RunAsync(messages, null, null, It.IsAny<CancellationToken>()), Times.Once);
    }

    private static Mock<Agent> CreateMockAgent(bool throwError)
    {
        var mockAgent = new Mock<Agent>();
        mockAgent.Setup(a => a.Id).Returns("test-agent-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns("Test Description");

        if (throwError)
        {
            mockAgent.Setup(a => a.RunAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
                .ThrowsAsync(new InvalidOperationException("Test error"));
        }
        else
        {
            var response = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"))
            {
                ResponseId = "test-response-id",
                Usage = new UsageDetails
                {
                    InputTokenCount = 10,
                    OutputTokenCount = 20
                }
            };

            mockAgent.Setup(a => a.RunAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
                .ReturnsAsync(response);
        }

        return mockAgent;
    }

    private static Mock<Agent> CreateMockStreamingAgent(bool throwError)
    {
        var mockAgent = new Mock<Agent>();
        mockAgent.Setup(a => a.Id).Returns("test-agent-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns("Test Description");

        if (throwError)
        {
            mockAgent.Setup(a => a.RunStreamingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
                .Returns(ThrowingAsyncEnumerable());
        }
        else
        {
            mockAgent.Setup(a => a.RunStreamingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
                .Returns(CreateStreamingResponse());
        }

        return mockAgent;

        static async IAsyncEnumerable<AgentRunResponseUpdate> ThrowingAsyncEnumerable([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            throw new InvalidOperationException("Streaming error");
#pragma warning disable CS0162 // Unreachable code detected
            yield break;
#pragma warning restore CS0162 // Unreachable code detected
        }

        static async IAsyncEnumerable<AgentRunResponseUpdate> CreateStreamingResponse([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            yield return new AgentRunResponseUpdate(ChatRole.Assistant, "Hello")
            {
                ResponseId = "stream-response-id"
            };

            yield return new AgentRunResponseUpdate(ChatRole.Assistant, " there!")
            {
                ResponseId = "stream-response-id"
            };

            yield return new AgentRunResponseUpdate
            {
                ResponseId = "stream-response-id",
                Contents = [new UsageContent(new UsageDetails
                {
                    InputTokenCount = 15,
                    OutputTokenCount = 25
                })]
            };
        }
    }

    [Fact]
    public void Constructor_NullAgent_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new OpenTelemetryAgent(null!));
    }

    [Fact]
    public void Constructor_WithParameters_SetsProperties()
    {
        // Arrange
        var mockAgent = new Mock<Agent>();
        mockAgent.Setup(a => a.Id).Returns("test-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns("Test Description");

        var logger = new Mock<ILogger>().Object;
        var sourceName = "custom-source";

        // Act
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, logger, sourceName);

        // Assert
        Assert.Equal("test-id", telemetryAgent.Id);
        Assert.Equal("TestAgent", telemetryAgent.Name);
        Assert.Equal("Test Description", telemetryAgent.Description);
    }

    [Fact]
    public void GetNewThread_DelegatesToInnerAgent()
    {
        // Arrange
        var mockThread = new Mock<AgentThread>().Object;
        var mockAgent = new Mock<Agent>();
        mockAgent.Setup(a => a.GetNewThread()).Returns(mockThread);

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object);

        // Act
        var result = telemetryAgent.GetNewThread();

        // Assert
        Assert.Same(mockThread, result);
        mockAgent.Verify(a => a.GetNewThread(), Times.Once);
    }

    [Fact]
    public void Dispose_DisposesResources()
    {
        // Arrange
        var mockAgent = new Mock<Agent>();
        var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object);

        // Act & Assert - Should not throw
        telemetryAgent.Dispose();
        telemetryAgent.Dispose(); // Should be safe to call multiple times
    }

    [Fact]
    public async Task RunAsync_WithNullResponseId_HandlesGracefullyAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockAgent = new Mock<Agent>();
        mockAgent.Setup(a => a.Id).Returns("test-agent-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");

        var response = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"))
        {
            ResponseId = null, // Null response ID
            Usage = null // Null usage
        };

        mockAgent.Setup(a => a.RunAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(response);

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);
        Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Response.MessageCount));
        Assert.Null(activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Response.Id));
        Assert.Null(activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Usage.InputTokens));
        Assert.Null(activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Usage.OutputTokens));
    }

    [Fact]
    public async Task RunAsync_WithEmptyAgentName_UsesOperationNameOnlyAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockAgent = new Mock<Agent>();
        mockAgent.Setup(a => a.Id).Returns("test-agent-id");
        mockAgent.Setup(a => a.Name).Returns((string?)null); // Null name

        var response = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"));
        mockAgent.Setup(a => a.RunAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(response);

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);
        Assert.Equal(AgentOpenTelemetryConsts.Agent.Run, activity.DisplayName);
    }

    [Fact]
    public async Task RunStreamingAsync_WithPartialUpdates_CombinesCorrectlyAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockAgent = new Mock<Agent>();
        mockAgent.Setup(a => a.Id).Returns("test-agent-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");

        mockAgent.Setup(a => a.RunStreamingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
            .Returns(CreatePartialStreamingResponse());

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Tell me a story")
        };

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in telemetryAgent.RunStreamingAsync(messages))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(4, updates.Count); // 3 content updates + 1 final update

        var activity = Assert.Single(activities);
        Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Response.MessageCount));
        Assert.Equal("partial-response-id", activity.GetTagItem(AgentOpenTelemetryConsts.Agent.Response.Id));

        static async IAsyncEnumerable<AgentRunResponseUpdate> CreatePartialStreamingResponse([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            yield return new AgentRunResponseUpdate(ChatRole.Assistant, "Once")
            {
                ResponseId = "partial-response-id"
            };

            yield return new AgentRunResponseUpdate(ChatRole.Assistant, " upon")
            {
                ResponseId = "partial-response-id"
            };

            yield return new AgentRunResponseUpdate(ChatRole.Assistant, " a time...")
            {
                ResponseId = "partial-response-id"
            };

            yield return new AgentRunResponseUpdate
            {
                ResponseId = "partial-response-id"
            };
        }
    }

    [Fact]
    public async Task RunAsync_DefaultSourceName_UsesCorrectSourceAsync()
    {
        // Arrange
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(AgentOpenTelemetryConsts.DefaultSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockAgent = CreateMockAgent(false);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object); // No custom source name

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);
        Assert.NotNull(activity);
        Assert.Equal(AgentOpenTelemetryConsts.DefaultSourceName, activity.Source.Name);
    }
}
