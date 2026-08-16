// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIAgentExtensions.AsIChatClient"/> method and the
/// <see cref="IChatClient"/> adapter it returns.
/// </summary>
public partial class AIAgentChatClientTests
{
    [Fact]
    public void AsIChatClient_WithNullAgent_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            AIAgentExtensions.AsIChatClient(null!));

        Assert.Equal("agent", exception.ParamName);
    }

    [Fact]
    public void AsIChatClient_WithValidAgent_ReturnsChatClient()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();

        // Act
        using var chatClient = mockAgent.Object.AsIChatClient();

        // Assert
        Assert.NotNull(chatClient);
        Assert.IsAssignableFrom<IChatClient>(chatClient);
    }

    [Fact]
    public async Task GetResponseAsync_WithNullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        using var chatClient = mockAgent.Object.AsIChatClient();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            chatClient.GetResponseAsync(null!));

        Assert.Equal("messages", exception.ParamName);
    }

    [Fact]
    public void GetStreamingResponseAsync_WithNullMessages_ThrowsSynchronously()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        using var chatClient = mockAgent.Object.AsIChatClient();

        // Act & Assert
        // The exception must be raised by the call itself, before any enumeration takes place,
        // which would not be the case if the method were implemented as an iterator.
        var exception = Assert.Throws<ArgumentNullException>(
            (Action)(() => chatClient.GetStreamingResponseAsync(null!)));

        Assert.Equal("messages", exception.ParamName);
    }

    [Fact]
    public async Task GetResponseAsync_WithoutChatOptions_ForwardsMessagesAndNullSessionAndOptionsAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        AgentSession? capturedSession = null;
        AgentRunOptions? capturedOptions = null;
        CancellationToken capturedCancellationToken = default;
        var invocationCount = 0;

        var agentResponse = new AgentResponse(new ChatMessage(ChatRole.Assistant, "Hello from the agent."));
        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                invocationCount++;
                capturedMessages = messages;
                capturedSession = session;
                capturedOptions = options;
                capturedCancellationToken = cancellationToken;
                return Task.FromResult(agentResponse);
            }
        };

        using var chatClient = agent.AsIChatClient();
        using var cancellationTokenSource = new CancellationTokenSource();
        List<ChatMessage> inputMessages = [new(ChatRole.User, "Hi")];

        // Act
        var response = await chatClient.GetResponseAsync(inputMessages, cancellationToken: cancellationTokenSource.Token);

        // Assert
        Assert.Equal(1, invocationCount);
        Assert.Same(inputMessages, capturedMessages);
        Assert.Null(capturedSession);
        Assert.Null(capturedOptions);
        Assert.Equal(cancellationTokenSource.Token, capturedCancellationToken);

        Assert.Equal("Hello from the agent.", response.Text);
        Assert.Same(agentResponse.Messages, response.Messages);
    }

    [Fact]
    public async Task GetResponseAsync_WithEmptyMessages_ForwardsEmptySequenceAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedMessages = messages;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "empty input accepted")));
            }
        };

        using var chatClient = agent.AsIChatClient();
        List<ChatMessage> inputMessages = [];

        // Act
        var response = await chatClient.GetResponseAsync(inputMessages);

        // Assert
        // An empty sequence is valid input and must reach the agent unchanged; only null is rejected.
        Assert.Same(inputMessages, capturedMessages);
        Assert.Empty(capturedMessages!);
        Assert.Equal("empty input accepted", response.Text);
    }

    [Fact]
    public async Task GetResponseAsync_WithChatOptions_ForwardsChatClientAgentRunOptionsAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            }
        };

        using var chatClient = agent.AsIChatClient();
        var chatOptions = new ChatOptions
        {
            Temperature = 0.5f,
            ResponseFormat = ChatResponseFormat.Json
        };

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions);

        // Assert
        var agentRunOptions = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions);
        Assert.Same(chatOptions, agentRunOptions.ChatOptions);
        Assert.Same(chatOptions.ResponseFormat, agentRunOptions.ResponseFormat);
    }

    [Fact]
    public async Task GetResponseAsync_WithBoundSession_ForwardsSessionAsync()
    {
        // Arrange
        AgentSession? capturedSession = null;
        var boundSession = new ChatClientAgentSession();

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedSession = session;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            }
        };

        using var chatClient = agent.AsIChatClient(boundSession);

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.Same(boundSession, capturedSession);
    }

    [Fact]
    public async Task GetResponseAsync_WithChatResponseRawRepresentation_ReturnsSameInstanceAsync()
    {
        // Arrange
        var innerChatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Hello"))
        {
            ConversationId = "conversation-42",
            ResponseId = "response-42"
        };

        var agentResponse = new AgentResponse(innerChatResponse);

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) => Task.FromResult(agentResponse)
        };

        using var chatClient = agent.AsIChatClient();

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.Same(innerChatResponse, response);
        Assert.Equal("conversation-42", response.ConversationId);
        Assert.Equal("response-42", response.ResponseId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_ConvertsUpdatesAndPropagatesCancellationTokenAsync()
    {
        // Arrange
        CancellationToken capturedCancellationToken = default;
        IEnumerable<ChatMessage>? capturedMessages = null;
        AgentSession? capturedSession = null;
        AgentRunOptions? capturedOptions = null;

        List<AgentResponseUpdate> updates =
        [
            new(ChatRole.Assistant, "Hello, ") { MessageId = "message-1" },
            new(ChatRole.Assistant, "world!") { MessageId = "message-1" }
        ];

        var boundSession = new ChatClientAgentSession();
        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedMessages = messages;
                capturedSession = session;
                capturedOptions = options;
                capturedCancellationToken = cancellationToken;
                return ToAsyncEnumerableAsync(updates, cancellationToken);
            }
        };

        using var chatClient = agent.AsIChatClient(boundSession);
        using var cancellationTokenSource = new CancellationTokenSource();
        List<ChatMessage> inputMessages = [new(ChatRole.User, "Hi")];
        var chatOptions = new ChatOptions();

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(inputMessages, chatOptions, cancellationTokenSource.Token))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        Assert.Same(inputMessages, capturedMessages);
        Assert.Same(boundSession, capturedSession);
        Assert.Same(chatOptions, Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions);
        Assert.Equal(cancellationTokenSource.Token, capturedCancellationToken);

        Assert.Equal(2, receivedUpdates.Count);
        Assert.Equal("Hello, ", receivedUpdates[0].Text);
        Assert.Equal(ChatRole.Assistant, receivedUpdates[0].Role);
        Assert.Equal("message-1", receivedUpdates[0].MessageId);
        Assert.Equal("world!", receivedUpdates[1].Text);
        Assert.Equal(ChatRole.Assistant, receivedUpdates[1].Role);
        Assert.Equal("message-1", receivedUpdates[1].MessageId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithCancellationSuppliedAtEnumeration_ForwardsTokenToAgentAsync()
    {
        // Arrange
        CancellationToken capturedCancellationToken = default;

        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedCancellationToken = cancellationToken;
                return ToAsyncEnumerableAsync<AgentResponseUpdate>([new(ChatRole.Assistant, "chunk")], cancellationToken);
            }
        };

        using var chatClient = agent.AsIChatClient();
        using var cancellationTokenSource = new CancellationTokenSource();

        // Act
        // No token is supplied to the call itself; it is attached at enumeration time instead, which only
        // reaches the agent if the streaming iterator honors [EnumeratorCancellation].
        var updates = chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        await foreach (var _ in updates.WithCancellation(cancellationTokenSource.Token))
        {
            // Enumerate to completion.
        }

        // Assert
        Assert.Equal(cancellationTokenSource.Token, capturedCancellationToken);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithChatResponseUpdateRawRepresentation_YieldsSameInstanceAsync()
    {
        // Arrange
        var innerUpdate = new ChatResponseUpdate(ChatRole.Assistant, "raw chunk") { MessageId = "message-7" };
        var agentUpdate = new AgentResponseUpdate(ChatRole.Assistant, "converted chunk")
        {
            RawRepresentation = innerUpdate
        };

        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
                ToAsyncEnumerableAsync<AgentResponseUpdate>([agentUpdate], cancellationToken)
        };

        using var chatClient = agent.AsIChatClient();

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        // Mirrors the response-level identity guarantee: an update that already carries a ChatResponseUpdate
        // raw representation is passed through rather than re-wrapped.
        var received = Assert.Single(receivedUpdates);
        Assert.Same(innerUpdate, received);
        Assert.Equal("raw chunk", received.Text);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithChatOptions_ForwardsChatClientAgentRunOptionsAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;

        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedOptions = options;
                return ToAsyncEnumerableAsync<AgentResponseUpdate>([new(ChatRole.Assistant, "chunk")], cancellationToken);
            }
        };

        using var chatClient = agent.AsIChatClient();
        var chatOptions = new ChatOptions { ResponseFormat = ChatResponseFormat.Json };

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions))
        {
            // Enumerate to completion.
        }

        // Assert
        var agentRunOptions = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions);
        Assert.Same(chatOptions, agentRunOptions.ChatOptions);
        Assert.Same(chatOptions.ResponseFormat, agentRunOptions.ResponseFormat);
    }

    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        using var chatClient = mockAgent.Object.AsIChatClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(
            (Action)(() => chatClient.GetService(null!)));

        Assert.Equal("serviceType", exception.ParamName);
    }

    [Fact]
    public void GetService_WithChatClientType_ReturnsAdapter()
    {
        // Arrange
        var agent = new TestAIAgent();
        using var chatClient = agent.AsIChatClient();

        // Act
        var service = chatClient.GetService(typeof(IChatClient));

        // Assert
        Assert.Same(chatClient, service);
    }

    [Fact]
    public void GetService_WithChatClientTypeOverChatClientAgent_ReturnsAdapterNotInnerClient()
    {
        // Arrange
        // ChatClientAgent.GetService(typeof(IChatClient)) returns its INNER chat client, so this agent is the
        // only one that can distinguish the adapter's self-check from the forward-to-agent branch. Backing the
        // adapter with a TestAIAgent would let those two branches be swapped without any test failing, while
        // silently unwrapping the agent pipeline.
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object);

        using var chatClient = agent.AsIChatClient();

        // Act
        var service = chatClient.GetService(typeof(IChatClient));

        // Assert
        Assert.Same(chatClient, service);
        Assert.NotSame(mockChatClient.Object, service);

        // Sanity check that forwarding first would have produced something else: the agent returns its own
        // (decorated) inner chat client, never the adapter. This is what makes the branch order load-bearing.
        var innerClientFromAgent = agent.GetService(typeof(IChatClient));
        Assert.NotNull(innerClientFromAgent);
        Assert.NotSame(chatClient, innerClientFromAgent);
    }

    [Fact]
    public void GetService_WithAgentType_ReturnsAgent()
    {
        // Arrange
        var agent = new TestAIAgent();
        using var chatClient = agent.AsIChatClient();

        // Act
        var service = chatClient.GetService(typeof(AIAgent));

        // Assert
        Assert.Same(agent, service);
    }

    [Fact]
    public void GetService_WithKeyedOrUnknownRequest_ForwardsToAgent()
    {
        // Arrange
        List<(Type ServiceType, object? ServiceKey)> capturedRequests = [];
        var keyedService = new object();

        var agent = new TestAIAgent
        {
            GetServiceFunc = (serviceType, serviceKey) =>
            {
                capturedRequests.Add((serviceType, serviceKey));
                return serviceKey is "key" ? keyedService : null;
            }
        };

        using var chatClient = agent.AsIChatClient();

        // Act
        var keyed = chatClient.GetService(typeof(IChatClient), "key");
        var unknown = chatClient.GetService(typeof(Uri));

        // Assert
        Assert.Same(keyedService, keyed);
        Assert.Null(unknown);
        Assert.Equal(2, capturedRequests.Count);
        Assert.Equal((typeof(IChatClient), "key"), capturedRequests[0]);
        Assert.Equal((typeof(Uri), (object?)null), capturedRequests[1]);
    }

    [Fact]
    public void GetService_WithChatClientMetadata_SynthesizesFromAgentMetadata()
    {
        // Arrange
        var agent = new TestAIAgent
        {
            GetServiceFunc = (serviceType, serviceKey) =>
                serviceType == typeof(AIAgentMetadata) ? new AIAgentMetadata("test-provider") : null
        };

        using var chatClient = agent.AsIChatClient();

        // Act
        var metadata = chatClient.GetService(typeof(ChatClientMetadata)) as ChatClientMetadata;
        var secondMetadata = chatClient.GetService(typeof(ChatClientMetadata)) as ChatClientMetadata;

        // Assert
        Assert.NotNull(metadata);
        Assert.Equal("test-provider", metadata!.ProviderName);
        Assert.Same(metadata, secondMetadata);
    }

    [Fact]
    public void GetService_WithChatClientMetadataProvidedByAgent_ReturnsAgentInstance()
    {
        // Arrange
        var agentProvidedMetadata = new ChatClientMetadata("agent-provided");
        var agent = new TestAIAgent
        {
            GetServiceFunc = (serviceType, serviceKey) =>
                serviceType == typeof(ChatClientMetadata) ? agentProvidedMetadata :
                serviceType == typeof(AIAgentMetadata) ? new AIAgentMetadata("synthesized") :
                null
        };

        using var chatClient = agent.AsIChatClient();

        // Act
        var metadata = chatClient.GetService(typeof(ChatClientMetadata));

        // Assert
        Assert.Same(agentProvidedMetadata, metadata);
    }

    [Fact]
    public async Task Dispose_IsNoOpAndIdempotentAsync()
    {
        // Arrange
        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
                Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "still alive")))
        };

        var chatClient = agent.AsIChatClient();

        // Act
        chatClient.Dispose();
        chatClient.Dispose();

        // Assert
        // Disposal does not own the agent, so the adapter remains usable and the agent is untouched.
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);
        Assert.Equal("still alive", response.Text);
    }

    [Fact]
    public async Task GetResponseAsync_OverChatClientAgent_AppliesAgentInstructionsAndToolsAsync()
    {
        // Arrange
        ChatOptions? capturedChatOptions = null;

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) => capturedChatOptions = options)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service."))
            {
                ConversationId = "conversation-out"
            });

        var agentTool = AIFunctionFactory.Create(() => "agent tool result", "AgentTool");
        var requestTool = AIFunctionFactory.Create(() => "request tool result", "RequestTool");

        var agent = new ChatClientAgent(
            mockChatClient.Object,
            instructions: "agent instructions",
            tools: [agentTool]);

        using var chatClient = agent.AsIChatClient();

        // Act
        var response = await chatClient.GetResponseAsync(
            [new ChatMessage(ChatRole.User, "Hi")],
            new ChatOptions
            {
                Instructions = "request instructions",
                ConversationId = "conversation-in",
                Tools = [requestTool]
            });

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equal("agent instructions\nrequest instructions", capturedChatOptions!.Instructions);
        Assert.Equal("conversation-in", capturedChatOptions.ConversationId);
        Assert.NotNull(capturedChatOptions.Tools);
        Assert.Contains(capturedChatOptions.Tools!, t => t.Name == "AgentTool");
        Assert.Contains(capturedChatOptions.Tools!, t => t.Name == "RequestTool");

        Assert.Equal("Response from the service.", response.Text);
        Assert.Equal("conversation-out", response.ConversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_OverChatClientAgent_StreamsThroughAgentPipelineAsync()
    {
        // Arrange
        ChatOptions? capturedChatOptions = null;

        List<ChatResponseUpdate> serviceUpdates =
        [
            new(ChatRole.Assistant, "Streamed ") { MessageId = "message-1" },
            new(ChatRole.Assistant, "from the service.") { MessageId = "message-1" }
        ];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, ct) =>
            {
                capturedChatOptions = options;
                return ToAsyncEnumerableAsync(serviceUpdates, ct);
            });

        var agent = new ChatClientAgent(mockChatClient.Object, instructions: "agent instructions");

        using var chatClient = agent.AsIChatClient();

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equal("agent instructions", capturedChatOptions!.Instructions);

        Assert.Equal(2, receivedUpdates.Count);
        Assert.Equal("Streamed from the service.", string.Concat(receivedUpdates.Select(u => u.Text)));
        Assert.All(receivedUpdates, u => Assert.Equal(ChatRole.Assistant, u.Role));
    }

    [Fact]
    public async Task GetResponseAsync_OverChatClientAgent_SupportsStructuredOutputAsync()
    {
        // Arrange
        ChatResponseFormat? capturedResponseFormat = null;
        var expectedResult = new WeatherReport { City = "Seattle", TemperatureCelsius = 12 };

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) => capturedResponseFormat = options?.ResponseFormat)
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(
                ChatRole.Assistant,
                JsonSerializer.Serialize(expectedResult, WeatherJsonContext.Default.WeatherReport))));

        var agent = new ChatClientAgent(mockChatClient.Object);

        using var chatClient = agent.AsIChatClient();

        // Act
        var response = await chatClient.GetResponseAsync<WeatherReport>(
            [new ChatMessage(ChatRole.User, "What is the weather in Seattle?")],
            WeatherJsonContext.Default.Options);

        // Assert
        Assert.IsType<ChatResponseFormatJson>(capturedResponseFormat);
        Assert.Equal(expectedResult.City, response.Result.City);
        Assert.Equal(expectedResult.TemperatureCelsius, response.Result.TemperatureCelsius);
    }

    /// <summary>
    /// Wraps a synchronous sequence in an asynchronous sequence for use by streaming tests.
    /// </summary>
    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(
        IEnumerable<T> items,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (var item in items)
        {
            cancellationToken.ThrowIfCancellationRequested();
            await Task.Yield();
            yield return item;
        }
    }

    /// <summary>
    /// A simple structured-output payload used by the end-to-end structured output test.
    /// </summary>
    private sealed class WeatherReport
    {
        public string? City { get; set; }

        public int TemperatureCelsius { get; set; }
    }

    [JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
    [JsonSerializable(typeof(WeatherReport))]
    private sealed partial class WeatherJsonContext : JsonSerializerContext;
}
