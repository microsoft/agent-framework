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
using OpenTelemetry.Metrics;
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

        var mockLogger = new Mock<ILogger>();
        var mockAgent = CreateMockAgent(withError);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, mockLogger.Object, sourceName);

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
        Assert.Equal($"{OpenTelemetryConsts.GenAI.Operation.NameValues.InvokeAgent} TestAgent", activity.DisplayName);
        Assert.Equal(ActivityKind.Client, activity.Kind);

        // Verify activity tags
        Assert.Equal(OpenTelemetryConsts.GenAI.Operation.NameValues.InvokeAgent, activity.GetTagItem(OpenTelemetryConsts.GenAI.Operation.Name));
        Assert.Equal(OpenTelemetryConsts.GenAI.SystemNameValues.MicrosoftExtensionsAIAgents, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));
        Assert.Equal("test-agent-id", activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Id));
        Assert.Equal("TestAgent", activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Name));
        Assert.Equal("Test Description", activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Description));

        if (withError)
        {
            Assert.Equal("System.InvalidOperationException", activity.GetTagItem(OpenTelemetryConsts.Error.Type));
            Assert.Equal(ActivityStatusCode.Error, activity.Status);
            Assert.Equal("Test error", activity.StatusDescription);
        }
        else
        {
            Assert.Equal("test-response-id", activity.GetTagItem(OpenTelemetryConsts.GenAI.Response.Id));
            Assert.Equal(10, activity.GetTagItem(OpenTelemetryConsts.GenAI.Usage.InputTokens));
            Assert.Equal(20, activity.GetTagItem(OpenTelemetryConsts.GenAI.Usage.OutputTokens));
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

        var mockAgent = CreateMockStreamingAgent(withError);
        var mockLogger = new Mock<ILogger>();
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, mockLogger.Object, sourceName);

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
        Assert.Equal($"{OpenTelemetryConsts.GenAI.Operation.NameValues.InvokeAgent} TestAgent", activity.DisplayName);
        Assert.Equal(ActivityKind.Client, activity.Kind);

        // Verify activity tags
        Assert.Equal(OpenTelemetryConsts.GenAI.Operation.NameValues.InvokeAgent, activity.GetTagItem(OpenTelemetryConsts.GenAI.Operation.Name));
        Assert.Equal(OpenTelemetryConsts.GenAI.SystemNameValues.MicrosoftExtensionsAIAgents, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));
        Assert.Equal("test-agent-id", activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Id));
        Assert.Equal("TestAgent", activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Name));
        Assert.Equal("Test Description", activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Description));

        if (withError)
        {
            Assert.Equal("System.InvalidOperationException", activity.GetTagItem(OpenTelemetryConsts.Error.Type));
            Assert.Equal(ActivityStatusCode.Error, activity.Status);
            Assert.Equal("Streaming error", activity.StatusDescription);
        }
        else
        {
            Assert.Equal("stream-response-id", activity.GetTagItem(OpenTelemetryConsts.GenAI.Response.Id));
            Assert.Equal(15, activity.GetTagItem(OpenTelemetryConsts.GenAI.Usage.InputTokens));
            Assert.Equal(25, activity.GetTagItem(OpenTelemetryConsts.GenAI.Usage.OutputTokens));
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
        Assert.Equal("You are a helpful assistant.", activity.GetTagItem(OpenTelemetryConsts.GenAI.Request.Instructions));
        // Should use default system when ChatClientMetadata is not available
        Assert.Equal(OpenTelemetryConsts.GenAI.SystemNameValues.MicrosoftExtensionsAIAgents, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));
    }

    [Fact]
    public async Task RunAsync_WithChatClientAgent_WithMetadata_UsesProviderNameAsync()
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

        // Setup ChatClientMetadata to return a specific provider name
        var metadata = new ChatClientMetadata("openai");
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(metadata);

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
        Assert.Equal("You are a helpful assistant.", activity.GetTagItem(OpenTelemetryConsts.GenAI.Request.Instructions));
        // Should use the provider name from ChatClientMetadata
        Assert.Equal("openai", activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));
    }

    [Fact]
    public async Task RunAsync_WithNonChatClientAgent_UsesDefaultSystemAsync()
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

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);
        // Should use default system when agent is not a ChatClientAgent
        Assert.Equal(OpenTelemetryConsts.GenAI.SystemNameValues.MicrosoftExtensionsAIAgents, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));
    }

    [Theory]
    [InlineData("azure")]
    [InlineData("openai")]
    [InlineData("custom-provider")]
    public async Task RunAsync_WithChatClientAgent_WithDifferentProviders_UsesCorrectSystemAsync(string providerName)
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

        // Setup ChatClientMetadata to return the specified provider name
        var metadata = new ChatClientMetadata(providerName);
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(metadata);

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Id = "chat-agent-id",
            Name = "ChatAgent"
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
        // Should use the provider name from ChatClientMetadata
        Assert.Equal(providerName, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));
    }

    [Fact]
    public async Task RunStreamingAsync_WithChatClientAgent_WithMetadata_UsesProviderNameAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockChatClient = new Mock<IChatClient>();
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "Stream response")
        ];
        mockChatClient.Setup(c => c.GetStreamingResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(returnUpdates.ToAsyncEnumerable());

        // Setup ChatClientMetadata to return a specific provider name
        var metadata = new ChatClientMetadata("azure");
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(metadata);

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
        await foreach (var update in telemetryAgent.RunStreamingAsync(messages))
        {
            // Consume the stream
        }

        // Assert
        var activity = Assert.Single(activities);
        Assert.Equal("You are a helpful assistant.", activity.GetTagItem(OpenTelemetryConsts.GenAI.Request.Instructions));
        // Should use the provider name from ChatClientMetadata
        Assert.Equal("azure", activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));
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
        Assert.Equal("thread-123", activity.GetTagItem(OpenTelemetryConsts.GenAI.Conversation.Id));
    }

    [Fact]
    public void WithOpenTelemetry_ExtensionMethod_CreatesOpenTelemetryAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");

        // Act
        using var telemetryAgent = mockAgent.Object.WithOpenTelemetry();

        // Assert
        Assert.IsType<OpenTelemetryAgent>(telemetryAgent);
        Assert.Equal("test-id", telemetryAgent.Id);
        Assert.Equal("TestAgent", telemetryAgent.Name);
    }

    #region ILogger Tests

    /// <summary>
    /// Verify that OpenTelemetryAgent constructor accepts ILogger parameter and uses it.
    /// </summary>
    [Fact]
    public void Constructor_WithILogger_AcceptsLoggerParameter()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        var mockLogger = new Mock<ILogger>();
        var sourceName = "test-source";

        // Act
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, mockLogger.Object, sourceName);

        // Assert
        Assert.Equal("test-id", telemetryAgent.Id);
        Assert.Equal("TestAgent", telemetryAgent.Name);
    }

    /// <summary>
    /// Verify that OpenTelemetryAgent constructor works with null ILogger parameter.
    /// </summary>
    [Fact]
    public void Constructor_WithNullILogger_UsesNullLogger()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        var sourceName = "test-source";

        // Act
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, logger: null, sourceName);

        // Assert
        Assert.Equal("test-id", telemetryAgent.Id);
        Assert.Equal("TestAgent", telemetryAgent.Name);
    }

    /// <summary>
    /// Verify that OpenTelemetryAgent uses the provided ILogger for logging events during RunAsync.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithILogger_LogsEventsCorrectlyAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var mockLogger = new Mock<ILogger>();

        // Setup the logger to return true for IsEnabled to ensure logging occurs
        mockLogger.Setup(x => x.IsEnabled(LogLevel.Information)).Returns(true);

        var mockAgent = CreateMockAgent(false);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, mockLogger.Object, sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        // Verify that the logger was called for logging events
        mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.IsAny<It.IsAnyType>(),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);
    }

    /// <summary>
    /// Verify that OpenTelemetryAgent extension method accepts ILogger parameter.
    /// </summary>
    [Fact]
    public void WithOpenTelemetry_ExtensionMethodWithILogger_CreatesOpenTelemetryAgentWithLogger()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        var mockLogger = new Mock<ILogger>();
        var sourceName = "test-source";

        // Act
        using var telemetryAgent = mockAgent.Object.WithOpenTelemetry(mockLogger.Object, sourceName);

        // Assert
        Assert.IsType<OpenTelemetryAgent>(telemetryAgent);
        Assert.Equal("test-id", telemetryAgent.Id);
        Assert.Equal("TestAgent", telemetryAgent.Name);
    }

    #endregion

    #region OpenTelemetry Logging Deduplication Tests

    /// <summary>
    /// Verify that when OpenTelemetryAgent wraps a ChatClientAgent with OpenTelemetry-enabled ChatClient,
    /// logs are not duplicated.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithOpenTelemetryChatClientAgent_DoesNotDuplicateLogsAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockLogger = new Mock<ILogger>();

        // Setup the logger to return true for IsEnabled to ensure logging occurs
        mockLogger.Setup(x => x.IsEnabled(LogLevel.Information)).Returns(true);

        var mockChatClient = new Mock<IChatClient>();

        // Setup ChatClient to return a response
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response")));

        // Setup ChatClientMetadata
        var metadata = new ChatClientMetadata("openai");
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(metadata);

        // Create a real OpenTelemetryChatClient to simulate OpenTelemetry-enabled ChatClient
        var openTelemetryChatClient = new OpenTelemetryChatClient(mockChatClient.Object, sourceName: sourceName);
        mockChatClient.Setup(c => c.GetService(typeof(OpenTelemetryChatClient), null)).Returns(openTelemetryChatClient);

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Id = "chat-agent-id",
            Name = "ChatAgent",
            Instructions = "You are a helpful assistant."
        });

        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent, mockLogger.Object, sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        // Verify that the logger was NOT called because OpenTelemetryChatClient is present (deduplication)
        mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.IsAny<It.IsAnyType>(),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Never);

        // Verify that activities were created (indicating telemetry is working)
        Assert.NotEmpty(activities);

        // Cleanup
        openTelemetryChatClient.Dispose();
    }

    /// <summary>
    /// Verify that OpenTelemetryAgent works correctly when wrapping a ChatClientAgent
    /// without OpenTelemetry-enabled ChatClient.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithRegularChatClientAgent_LogsCorrectlyAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockLogger = new Mock<ILogger>();

        // Setup the logger to return true for IsEnabled to ensure logging occurs
        mockLogger.Setup(x => x.IsEnabled(LogLevel.Information)).Returns(true);

        var mockChatClient = new Mock<IChatClient>();

        // Setup ChatClient to return a response
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response")));

        // Setup ChatClientMetadata
        var metadata = new ChatClientMetadata("openai");
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(metadata);

        // No OpenTelemetryChatClient setup - simulating regular ChatClient
        mockChatClient.Setup(c => c.GetService(typeof(OpenTelemetryChatClient), null)).Returns((OpenTelemetryChatClient?)null);

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Id = "chat-agent-id",
            Name = "ChatAgent",
            Instructions = "You are a helpful assistant."
        });

        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent, mockLogger.Object, sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        // Verify that the logger was called
        mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.IsAny<It.IsAnyType>(),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);

        // Verify that activities were created
        Assert.NotEmpty(activities);
    }

    /// <summary>
    /// Verify that EnableSensitiveData setting is inherited from OpenTelemetryChatClient when available.
    /// </summary>
    [Fact]
    public void Constructor_WithOpenTelemetryChatClient_InheritsEnableSensitiveDataSetting()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var mockChatClient = new Mock<IChatClient>();

        // Setup ChatClientMetadata
        var metadata = new ChatClientMetadata("openai");
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(metadata);

        // Create a real OpenTelemetryChatClient with EnableSensitiveData = true
        var openTelemetryChatClient = new OpenTelemetryChatClient(mockChatClient.Object, sourceName: sourceName)
        {
            EnableSensitiveData = true
        };
        mockChatClient.Setup(c => c.GetService(typeof(OpenTelemetryChatClient), null)).Returns(openTelemetryChatClient);

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Id = "chat-agent-id",
            Name = "ChatAgent"
        });

        // Act
        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent, sourceName: sourceName);

        // Assert
        Assert.True(telemetryAgent.EnableSensitiveData);

        // Cleanup
        openTelemetryChatClient.Dispose();
    }

    #endregion

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns ActivitySource when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingActivitySource_ReturnsActivitySource()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-id");
        var sourceName = "test-source";
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        // Act
        var result = telemetryAgent.GetService(typeof(ActivitySource));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<ActivitySource>(result);
        var activitySource = (ActivitySource)result;
        Assert.Equal(sourceName, activitySource.Name);
    }

    /// <summary>
    /// Verify that GetService delegates to inner agent for unknown service types.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnknownServiceType_DelegatesToInnerAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var customService = new object();
        mockAgent.Setup(a => a.GetService(typeof(string), null))
            .Returns(customService);

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object);

        // Act
        var result = telemetryAgent.GetService(typeof(string));

        // Assert
        Assert.Same(customService, result);
        mockAgent.Verify(a => a.GetService(typeof(string), null), Times.Once);
    }

    /// <summary>
    /// Verify that GetService returns null for unknown service types when inner agent returns null.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnknownServiceTypeWithNullFromInnerAgent_ReturnsNull()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.GetService(typeof(string), null))
            .Returns((object?)null);

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object);

        // Act
        var result = telemetryAgent.GetService(typeof(string));

        // Assert
        Assert.Null(result);
        mockAgent.Verify(a => a.GetService(typeof(string), null), Times.Once);
    }

    /// <summary>
    /// Verify that GetService with serviceKey parameter delegates correctly to inner agent.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_DelegatesToInnerAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var customService = new object();
        var serviceKey = "test-key";
        mockAgent.Setup(a => a.GetService(typeof(string), serviceKey))
            .Returns(customService);

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object);

        // Act
        var result = telemetryAgent.GetService(typeof(string), serviceKey);

        // Assert
        Assert.Same(customService, result);
        mockAgent.Verify(a => a.GetService(typeof(string), serviceKey), Times.Once);
    }

    /// <summary>
    /// Verify that GetService returns ActivitySource even when inner agent has the same service type.
    /// </summary>
    [Fact]
    public void GetService_RequestingActivitySourceWithInnerAgentHavingSameType_ReturnsOpenTelemetryActivitySource()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var innerActivitySource = new ActivitySource("inner-source");
        mockAgent.Setup(a => a.GetService(typeof(ActivitySource), null))
            .Returns(innerActivitySource);

        var sourceName = "telemetry-source";
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        // Act
        var result = telemetryAgent.GetService(typeof(ActivitySource));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<ActivitySource>(result);
        var activitySource = (ActivitySource)result;
        Assert.Equal(sourceName, activitySource.Name);
        Assert.NotSame(innerActivitySource, result); // Should return OpenTelemetryAgent's ActivitySource, not inner agent's

        // Cleanup
        innerActivitySource.Dispose();
    }

    /// <summary>
    /// Verify that GetService can retrieve AIAgentMetadata from inner agent.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_DelegatesToInnerAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var agentMetadata = new AIAgentMetadata("test-provider");
        mockAgent.Setup(a => a.GetService(typeof(AIAgentMetadata), null))
            .Returns(agentMetadata);

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object);

        // Act
        var result = telemetryAgent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.Same(agentMetadata, result);
        mockAgent.Verify(a => a.GetService(typeof(AIAgentMetadata), null), Times.AtLeastOnce);
    }

    /// <summary>
    /// Verify that OpenTelemetryAgent delegates AIAgentMetadata requests to inner agent.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_DelegatesToInnerAgentWithChatClientAgent()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var chatClientMetadata = new ChatClientMetadata("test-provider");
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata);

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Instructions = "Test instructions"
        });

        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent);

        // Act
        var result = telemetryAgent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<AIAgentMetadata>(result);
        var agentMetadata = (AIAgentMetadata)result;
        Assert.Equal("test-provider", agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that when OpenTelemetryAgent wraps a ChatClientAgent, the AIAgentMetadata.ProviderName
    /// from ChatClientMetadata is correctly reflected in OpenTelemetry activities.
    /// </summary>
    [Theory]
    [InlineData("openai")]
    [InlineData("azure")]
    [InlineData("anthropic")]
    [InlineData("custom-provider")]
    public async Task RunAsync_WithChatClientAgent_ProviderNameReflectedInTelemetryAsync(string providerName)
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockChatClient = new Mock<IChatClient>();
        var chatClientMetadata = new ChatClientMetadata(providerName);
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata);
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response")));

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Instructions = "Test instructions"
        });

        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);

        // Verify that the provider name from ChatClientMetadata appears in telemetry
        Assert.Equal(providerName, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));

        // Verify that GetService returns the same provider name
        var agentMetadata = telemetryAgent.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;
        Assert.NotNull(agentMetadata);
        Assert.Equal(providerName, agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that when OpenTelemetryAgent wraps a ChatClientAgent with null ChatClientMetadata,
    /// the system defaults to "Microsoft.Extensions.AI" in telemetry.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithChatClientAgent_NullMetadata_DefaultsToMEAIAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockChatClient = new Mock<IChatClient>();
        // Setup ChatClient to return null metadata
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns((ChatClientMetadata?)null);
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response")));

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Instructions = "Test instructions"
        });

        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);

        // Verify that the system defaults to "microsoft.extensions.ai.agents" when no metadata is available
        Assert.Equal("microsoft.extensions.ai.agents", activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));

        // Verify that GetService returns null provider name
        var agentMetadata = telemetryAgent.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;
        Assert.NotNull(agentMetadata);
        Assert.Null(agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that when OpenTelemetryAgent wraps a non-ChatClientAgent with custom metadata,
    /// the custom provider name is correctly reflected in telemetry.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithCustomAgent_CustomMetadata_ReflectedInTelemetryAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var customProviderName = "custom-ai-provider";
        var mockAgent = new Mock<AIAgent>();
        var customMetadata = new AIAgentMetadata(customProviderName);

        // Setup mock agent to return custom metadata
        mockAgent.Setup(a => a.GetService(typeof(AIAgentMetadata), null))
            .Returns(customMetadata);
        mockAgent.Setup(a => a.RunAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Custom response")));

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);

        // Verify that the custom provider name appears in telemetry
        Assert.Equal(customProviderName, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));

        // Verify that GetService returns the same custom provider name
        var agentMetadata = telemetryAgent.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;
        Assert.NotNull(agentMetadata);
        Assert.Equal(customProviderName, agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that when OpenTelemetryAgent wraps a non-ChatClientAgent with no metadata,
    /// the system defaults to "Microsoft.Extensions.AI" in telemetry.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithCustomAgent_NoMetadata_DefaultsToMEAIAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockAgent = new Mock<AIAgent>();

        // Setup mock agent to return null metadata
        mockAgent.Setup(a => a.GetService(typeof(AIAgentMetadata), null))
            .Returns((AIAgentMetadata?)null);
        mockAgent.Setup(a => a.RunAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<AgentThread>(), It.IsAny<AgentRunOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Response")));

        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert
        var activity = Assert.Single(activities);

        // Verify that the system defaults to "microsoft.extensions.ai.agents" when no metadata is available
        Assert.Equal("microsoft.extensions.ai.agents", activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));

        // Verify that GetService returns null for metadata
        var agentMetadata = telemetryAgent.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;
        Assert.Null(agentMetadata);
    }

    /// <summary>
    /// Verify that streaming operations also correctly reflect provider name in telemetry.
    /// </summary>
    [Theory]
    [InlineData("openai")]
    [InlineData("azure")]
    [InlineData("anthropic")]
    public async Task RunStreamingAsync_WithChatClientAgent_ProviderNameReflectedInTelemetryAsync(string providerName)
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockChatClient = new Mock<IChatClient>();
        var chatClientMetadata = new ChatClientMetadata(providerName);
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata);

        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "Hello"),
            new ChatResponseUpdate(role: ChatRole.Assistant, content: " World"),
        ];

        mockChatClient.Setup(c => c.GetStreamingResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(returnUpdates.ToAsyncEnumerable());

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Instructions = "Test instructions"
        });

        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await foreach (var update in telemetryAgent.RunStreamingAsync(messages))
        {
            // Process updates
        }

        // Assert
        var activity = Assert.Single(activities);

        // Verify that the provider name from ChatClientMetadata appears in telemetry
        Assert.Equal(providerName, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));

        // Verify that GetService returns the same provider name
        var agentMetadata = telemetryAgent.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;
        Assert.NotNull(agentMetadata);
        Assert.Equal(providerName, agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that provider name consistency is maintained across multiple RunAsync calls.
    /// </summary>
    [Fact]
    public async Task RunAsync_MultipleCallsWithSameAgent_ConsistentProviderNameAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var providerName = "consistent-provider";
        var mockChatClient = new Mock<IChatClient>();
        var chatClientMetadata = new ChatClientMetadata(providerName);
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata);
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response")));

        var chatClientAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Instructions = "Test instructions"
        });

        using var telemetryAgent = new OpenTelemetryAgent(chatClientAgent, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act - Make multiple calls
        await telemetryAgent.RunAsync(messages);
        await telemetryAgent.RunAsync(messages);
        await telemetryAgent.RunAsync(messages);

        // Assert
        Assert.Equal(3, activities.Count);

        // Verify that all activities have the same provider name
        foreach (var activity in activities)
        {
            Assert.Equal(providerName, activity.GetTagItem(OpenTelemetryConsts.GenAI.SystemName));
        }

        // Verify that GetService consistently returns the same provider name
        var agentMetadata1 = telemetryAgent.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;
        var agentMetadata2 = telemetryAgent.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;
        Assert.NotNull(agentMetadata1);
        Assert.NotNull(agentMetadata2);
        Assert.Equal(providerName, agentMetadata1.ProviderName);
        Assert.Equal(providerName, agentMetadata2.ProviderName);
        Assert.Same(agentMetadata1, agentMetadata2); // Should be cached
    }

    #endregion

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

    private static Mock<AIAgent> CreateMockAgent(bool throwError)
    {
        var mockAgent = new Mock<AIAgent>();
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

    private static Mock<AIAgent> CreateMockStreamingAgent(bool throwError)
    {
        var mockAgent = new Mock<AIAgent>();
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
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns("Test Description");
        var mockLogger = new Mock<ILogger>();

        var logger = new Mock<ILogger>().Object;
        var sourceName = "custom-source";

        // Act
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, mockLogger.Object, sourceName);

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
        var mockAgent = new Mock<AIAgent>();
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
        var mockAgent = new Mock<AIAgent>();
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

        var mockAgent = new Mock<AIAgent>();
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
        Assert.Null(activity.GetTagItem(OpenTelemetryConsts.GenAI.Response.Id));
        Assert.Null(activity.GetTagItem(OpenTelemetryConsts.GenAI.Usage.InputTokens));
        Assert.Null(activity.GetTagItem(OpenTelemetryConsts.GenAI.Usage.OutputTokens));
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

        var mockAgent = new Mock<AIAgent>();
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
        Assert.Equal(OpenTelemetryConsts.GenAI.Operation.NameValues.InvokeAgent, activity.DisplayName);
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

        var mockAgent = new Mock<AIAgent>();
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
        Assert.Equal("partial-response-id", activity.GetTagItem(OpenTelemetryConsts.GenAI.Response.Id));

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
            .AddSource(OpenTelemetryConsts.DefaultSourceName)
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
        Assert.Equal(OpenTelemetryConsts.DefaultSourceName, activity.Source.Name);
    }

    [Fact]
    public async Task RunAsync_WithMetricsEnabled_RecordsMetricsAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        var exportedMetrics = new List<Metric>();

        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using var meterProvider = OpenTelemetry.Sdk.CreateMeterProviderBuilder()
            .AddMeter(sourceName)
            .AddInMemoryExporter(exportedMetrics)
            .Build();

        var mockAgent = CreateMockAgent(false);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act
        await telemetryAgent.RunAsync(messages);

        // Force metric collection
        meterProvider.ForceFlush(5000);

        // Assert - Verify metrics were recorded
        Assert.NotEmpty(exportedMetrics);

        // Check for operation duration metric
        var durationMetric = exportedMetrics.FirstOrDefault(m => m.Name == OpenTelemetryConsts.GenAI.Client.OperationDuration.Name);
        Assert.NotNull(durationMetric);

        // Check for token usage metric
        var tokenUsageMetric = exportedMetrics.FirstOrDefault(m => m.Name == OpenTelemetryConsts.GenAI.Client.TokenUsage.Name);
        Assert.NotNull(tokenUsageMetric);
    }

    [Fact]
    public async Task RunAsync_WithMetricsEnabledAndError_RecordsErrorMetricsAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        var exportedMetrics = new List<Metric>();

        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using var meterProvider = OpenTelemetry.Sdk.CreateMeterProviderBuilder()
            .AddMeter(sourceName)
            .AddInMemoryExporter(exportedMetrics)
            .Build();

        var mockAgent = CreateMockAgent(true); // With error
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName: sourceName);

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello")
        };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => telemetryAgent.RunAsync(messages));

        // Force metric collection
        meterProvider.ForceFlush(5000);

        // Assert - Verify error metrics were recorded
        Assert.NotEmpty(exportedMetrics);

        // Check for operation duration metric with error tag
        var durationMetric = exportedMetrics.FirstOrDefault(m => m.Name == OpenTelemetryConsts.GenAI.Client.OperationDuration.Name);
        Assert.NotNull(durationMetric);
    }

    [Fact]
    public async Task RunStreamingAsync_WithMetricsEnabled_RecordsMetricsAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        var exportedMetrics = new List<Metric>();

        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        using var meterProvider = OpenTelemetry.Sdk.CreateMeterProviderBuilder()
            .AddMeter(sourceName)
            .AddInMemoryExporter(exportedMetrics)
            .Build();

        var mockAgent = CreateMockStreamingAgent(false);
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

        // Force metric collection
        meterProvider.ForceFlush(5000);

        // Assert - Verify metrics were recorded
        Assert.NotEmpty(exportedMetrics);
        Assert.NotEmpty(updates);

        // Check for operation duration metric
        var durationMetric = exportedMetrics.FirstOrDefault(m => m.Name == OpenTelemetryConsts.GenAI.Client.OperationDuration.Name);
        Assert.NotNull(durationMetric);

        // Check for token usage metric
        var tokenUsageMetric = exportedMetrics.FirstOrDefault(m => m.Name == OpenTelemetryConsts.GenAI.Client.TokenUsage.Name);
        Assert.NotNull(tokenUsageMetric);
    }

    [Fact]
    public async Task RunAsync_WithNullUsage_SkipsTokenMetricsAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var exportedMetrics = new List<Metric>();

        using var meterProvider = OpenTelemetry.Sdk.CreateMeterProviderBuilder()
            .AddMeter(sourceName)
            .AddInMemoryExporter(exportedMetrics)
            .Build();

        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-agent-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");

        // Response with null usage
        var response = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"))
        {
            ResponseId = "test-response-id",
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

        // Force metric collection
        meterProvider.ForceFlush(5000);

        // Assert - Should have duration and request count metrics, but no token usage metrics
        var durationMetric = exportedMetrics.FirstOrDefault(m => m.Name == OpenTelemetryConsts.GenAI.Client.OperationDuration.Name);
        Assert.NotNull(durationMetric);

        // Token usage metric should not be recorded when usage is null
        var tokenUsageMetric = exportedMetrics.FirstOrDefault(m => m.Name == OpenTelemetryConsts.GenAI.Client.TokenUsage.Name);
        Assert.Null(tokenUsageMetric);
    }

    [Fact]
    public async Task RunAsync_WithMetricsDisabled_SkipsMetricRecordingAsync()
    {
        // Arrange - No meter provider, so metrics are disabled
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

        // Act
        await telemetryAgent.RunAsync(messages);

        // Assert - Should complete without recording metrics (since no meter provider)
        var activity = Assert.Single(activities);
        Assert.NotNull(activity);

        // Verify the agent was called
        mockAgent.Verify(a => a.RunAsync(messages, null, null, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task RunAsync_WithPartialTokenUsage_RecordsAvailableTokensAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var exportedMetrics = new List<Metric>();

        using var meterProvider = OpenTelemetry.Sdk.CreateMeterProviderBuilder()
            .AddMeter(sourceName)
            .AddInMemoryExporter(exportedMetrics)
            .Build();

        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-agent-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");

        // Response with only input tokens (no output tokens)
        var response = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"))
        {
            ResponseId = "test-response-id",
            Usage = new UsageDetails
            {
                InputTokenCount = 10,
                OutputTokenCount = null // No output tokens
            }
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

        // Force metric collection
        meterProvider.ForceFlush(5000);

        // Assert - Should record input tokens but not output tokens
        var tokenUsageMetric = exportedMetrics.FirstOrDefault(m => m.Name == OpenTelemetryConsts.GenAI.Client.TokenUsage.Name);
        Assert.NotNull(tokenUsageMetric);
    }

    [Fact]
    public async Task RunAsync_WithNullDescription_SkipsDescriptionAttributeAsync()
    {
        // Arrange
        var sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Id).Returns("test-agent-id");
        mockAgent.Setup(a => a.Name).Returns("TestAgent");
        mockAgent.Setup(a => a.Description).Returns((string?)null); // Null description

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
        Assert.Equal("test-agent-id", activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Id));
        Assert.Equal("TestAgent", activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Name));

        // Description should not be present when null
        Assert.Null(activity.GetTagItem(OpenTelemetryConsts.GenAI.Agent.Description));
    }
}
