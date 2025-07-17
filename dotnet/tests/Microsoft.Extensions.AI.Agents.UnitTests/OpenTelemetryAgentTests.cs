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

        var mockAgent = CreateMockAgent(withError);
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName);

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
        Assert.Equal($"{AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent} TestAgent", activity.DisplayName);
        Assert.Equal(ActivityKind.Client, activity.Kind);

        // Verify activity tags
        Assert.Equal(AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.OperationName));
        Assert.Equal(AgentOpenTelemetryConsts.GenAI.Systems.MicrosoftExtensionsAI, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.System));
        Assert.Equal("test-agent-id", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Id));
        Assert.Equal("TestAgent", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Name));
        Assert.Equal("Test Description", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Description));
        Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Request.MessageCount));

        if (withError)
        {
            Assert.Equal("System.InvalidOperationException", activity.GetTagItem(AgentOpenTelemetryConsts.ErrorInfo.Type));
            Assert.Equal(ActivityStatusCode.Error, activity.Status);
            Assert.Equal("Test error", activity.StatusDescription);
        }
        else
        {
            Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Response.MessageCount));
            Assert.Equal("test-response-id", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Response.Id));
            Assert.Equal(10, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Usage.InputTokens));
            Assert.Equal(20, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Usage.OutputTokens));
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
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName);

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
        Assert.Equal($"{AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent} TestAgent", activity.DisplayName);
        Assert.Equal(ActivityKind.Client, activity.Kind);

        // Verify activity tags
        Assert.Equal(AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.OperationName));
        Assert.Equal(AgentOpenTelemetryConsts.GenAI.Systems.MicrosoftExtensionsAI, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.System));
        Assert.Equal("test-agent-id", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Id));
        Assert.Equal("TestAgent", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Name));
        Assert.Equal("Test Description", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Description));
        Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Request.MessageCount));

        if (withError)
        {
            Assert.Equal("System.InvalidOperationException", activity.GetTagItem(AgentOpenTelemetryConsts.ErrorInfo.Type));
            Assert.Equal(ActivityStatusCode.Error, activity.Status);
            Assert.Equal("Streaming error", activity.StatusDescription);
        }
        else
        {
            Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Response.MessageCount));
            Assert.Equal("stream-response-id", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Response.Id));
            Assert.Equal(15, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Usage.InputTokens));
            Assert.Equal(25, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Usage.OutputTokens));
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
        Assert.Equal("You are a helpful assistant.", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Request.Instructions));
        // Should use default system when ChatClientMetadata is not available
        Assert.Equal(AgentOpenTelemetryConsts.GenAI.Systems.MicrosoftExtensionsAI, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.System));
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
        Assert.Equal("You are a helpful assistant.", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Request.Instructions));
        // Should use the provider name from ChatClientMetadata
        Assert.Equal("openai", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.System));
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
        Assert.Equal(AgentOpenTelemetryConsts.GenAI.Systems.MicrosoftExtensionsAI, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.System));
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
        Assert.Equal(providerName, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.System));
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
        Assert.Equal("You are a helpful assistant.", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Request.Instructions));
        // Should use the provider name from ChatClientMetadata
        Assert.Equal("azure", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.System));
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
        Assert.Equal("thread-123", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.ConversationId));
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
        using var telemetryAgent = new OpenTelemetryAgent(mockAgent.Object, sourceName);

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
        Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Response.MessageCount));
        Assert.Null(activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Response.Id));
        Assert.Null(activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Usage.InputTokens));
        Assert.Null(activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Usage.OutputTokens));
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
        Assert.Equal(AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent, activity.DisplayName);
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
        Assert.Equal(1, activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Response.MessageCount));
        Assert.Equal("partial-response-id", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Response.Id));

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
        var durationMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.OperationDuration.Name);
        Assert.NotNull(durationMetric);

        // Check for request count metric
        var requestCountMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.RequestCount.Name);
        Assert.NotNull(requestCountMetric);

        // Check for token usage metric
        var tokenUsageMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.TokenUsage.Name);
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
        var durationMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.OperationDuration.Name);
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
        var durationMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.OperationDuration.Name);
        Assert.NotNull(durationMetric);

        // Check for request count metric
        var requestCountMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.RequestCount.Name);
        Assert.NotNull(requestCountMetric);

        // Check for token usage metric
        var tokenUsageMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.TokenUsage.Name);
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

        var mockAgent = new Mock<Agent>();
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
        var durationMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.OperationDuration.Name);
        Assert.NotNull(durationMetric);

        var requestCountMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.RequestCount.Name);
        Assert.NotNull(requestCountMetric);

        // Token usage metric should not be recorded when usage is null
        var tokenUsageMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.TokenUsage.Name);
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

        var mockAgent = new Mock<Agent>();
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
        var tokenUsageMetric = exportedMetrics.FirstOrDefault(m => m.Name == AgentOpenTelemetryConsts.GenAI.Agent.Client.TokenUsage.Name);
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

        var mockAgent = new Mock<Agent>();
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
        Assert.Equal("test-agent-id", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Id));
        Assert.Equal("TestAgent", activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Name));

        // Description should not be present when null
        Assert.Null(activity.GetTagItem(AgentOpenTelemetryConsts.GenAI.Agent.Description));
    }
}
