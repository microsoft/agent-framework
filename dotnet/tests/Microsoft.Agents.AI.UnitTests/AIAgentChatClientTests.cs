// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
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
                ToAsyncEnumerableAsync([agentUpdate], cancellationToken)
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
        Assert.Equal((typeof(Uri), null), capturedRequests[1]);
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

    [Fact]
    public void AsIChatClient_WithConversationIdAndNoSession_ThrowsArgumentException()
    {
        // Arrange
        var agent = new TestAIAgent();

        // Act & Assert
        // A conversation id only signals "history is stored here"; without a session there is nothing storing it.
        var exception = Assert.Throws<ArgumentException>(() =>
            agent.AsIChatClient(session: null, conversationId: "orphan-conversation"));

        Assert.Equal("conversationId", exception.ParamName);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void AsIChatClient_WithBlankConversationId_ThrowsArgumentException(string conversationId)
    {
        // Arrange
        var agent = new TestAIAgent();

        // Act & Assert
        // A blank id would be reported verbatim on every response, where a caller testing it with
        // string.IsNullOrEmpty reads "no stored history" and resends everything the session already holds.
        var exception = Assert.Throws<ArgumentException>(() =>
            agent.AsIChatClient(new ChatClientAgentSession(), conversationId));

        Assert.Equal("conversationId", exception.ParamName);
    }

    [Fact]
    public void AsIChatClient_WithReservedConversationId_ThrowsArgumentException()
    {
        // Arrange
        var agent = new TestAIAgent();

        // Act & Assert
        // The framework stamps this value to mark history as handled in process. Accepting it here would make an
        // internal marker indistinguishable from a conversation a caller can resume.
        var exception = Assert.Throws<ArgumentException>(() =>
            agent.AsIChatClient(
                new ChatClientAgentSession(),
                PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId));

        Assert.Equal("conversationId", exception.ParamName);
    }

    [Fact]
    public async Task GetResponseAsync_WithBoundSession_ReturnsStableSyntheticConversationIdAsync()
    {
        // Arrange
        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
                Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")))
        };

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession());
        using var otherChatClient = agent.AsIChatClient(new ChatClientAgentSession());

        // Act
        var first = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);
        var second = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Again")]);
        var other = await otherChatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        // The bound session stores the history, so the response must say so; the id is per adapter instance,
        // never a shared constant, so an id minted over one session cannot be replayed against another.
        Assert.NotNull(first.ConversationId);
        Assert.Equal(first.ConversationId, second.ConversationId);
        Assert.NotEqual(first.ConversationId, other.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithDeveloperSuppliedConversationId_UsesItVerbatimAsync()
    {
        // Arrange
        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
                Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")))
        };

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "my-own-conversation-id");

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.Equal("my-own-conversation-id", response.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithBoundSessionAndServiceManagedResponse_ReturnsResponseUntouchedAsync()
    {
        // Arrange
        var innerChatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Hello"))
        {
            ConversationId = "service-conversation"
        };

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) => Task.FromResult(new AgentResponse(innerChatResponse))
        };

        // The session stands behind the id the response carries, which is the state a real ChatClientAgent leaves
        // behind: it records the service id on the session as the run ends, before the adapter inspects either.
        var session = new ChatClientAgentSession("service-conversation");
        using var chatClient = agent.AsIChatClient(session, "adapter-conversation");

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        // A real service-managed id outranks the synthetic one, and the response is returned as the inner
        // client produced it rather than copied.
        Assert.Same(innerChatResponse, response);
        Assert.Equal("service-conversation", response.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithSessionKnowingServiceConversationId_StampsKnownIdAsync()
    {
        // Arrange
        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
                Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")))
        };

        var session = new ChatClientAgentSession("known-service-conversation");
        using var chatClient = agent.AsIChatClient(session, "adapter-conversation");

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        // The session learned a real id on an earlier turn, so that is what the caller must be told, even
        // though this particular response did not carry one.
        Assert.Equal("known-service-conversation", response.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithEchoedAdapterConversationId_StripsItBeforeTheAgentSeesItAsync()
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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");
        var chatOptions = new ChatOptions { ConversationId = "adapter-conversation", Temperature = 0.25f };

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions);

        // Assert
        // Stripping the echoed id restores as-if-absent semantics, matching turn one; the strip happens on a
        // copy so the caller's own options object is never mutated.
        var forwarded = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions;
        Assert.NotNull(forwarded);
        Assert.NotSame(chatOptions, forwarded);
        Assert.Null(forwarded!.ConversationId);
        Assert.Equal(0.25f, forwarded.Temperature);
        Assert.Equal("adapter-conversation", chatOptions.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithEchoedServiceConversationId_ForwardsOptionsUntouchedAsync()
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

        var session = new ChatClientAgentSession("known-service-conversation");
        using var chatClient = agent.AsIChatClient(session, "adapter-conversation");
        var chatOptions = new ChatOptions { ConversationId = "known-service-conversation" };

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions);

        // Assert
        // The id names the session's own service conversation, so it is passed through for the agent to
        // validate rather than being second-guessed here.
        Assert.Same(chatOptions, Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions);
    }

    [Fact]
    public async Task GetResponseAsync_WithForeignConversationId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        // RunAsyncFunc is left at its throwing default: the request must be rejected before it reaches the agent.
        var agent = new TestAIAgent();
        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            chatClient.GetResponseAsync(
                [new ChatMessage(ChatRole.User, "Hi")],
                new ChatOptions { ConversationId = "someone-elses-conversation" }));

        Assert.Contains("AsIChatClient", exception.Message, StringComparison.Ordinal);
        Assert.Contains("CreateSessionAsync", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetResponseAsync_WithBoundSessionAndNoConversationId_ReusesBoundSessionAsync()
    {
        // Arrange
        List<AgentSession?> capturedSessions = [];
        var boundSession = new ChatClientAgentSession();

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedSessions.Add(session);
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            }
        };

        using var chatClient = agent.AsIChatClient(boundSession);

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Again")], new ChatOptions());

        // Assert
        // A fixed bound session cannot fork, so an absent id means "keep going" rather than "start fresh".
        Assert.Equal(2, capturedSessions.Count);
        Assert.All(capturedSessions, session => Assert.Same(boundSession, session));
    }

    [Fact]
    public async Task GetResponseAsync_WhenStampingSyntheticConversationId_PreservesEveryResponseMemberAsync()
    {
        // Arrange
        List<ChatMessage> messages = [new(ChatRole.Assistant, "Hello")];
        var rawRepresentation = new object();
        var usage = new UsageDetails { InputTokenCount = 11, OutputTokenCount = 22 };
        var additionalProperties = new AdditionalPropertiesDictionary { ["key"] = "value" };
        var continuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        var createdAt = new DateTimeOffset(2024, 1, 2, 3, 4, 5, TimeSpan.Zero);

        var innerChatResponse = new ChatResponse
        {
            Messages = messages,
            ResponseId = "response-id",
            ModelId = "model-id",
            CreatedAt = createdAt,
            FinishReason = ChatFinishReason.Stop,
            Usage = usage,
            AdditionalProperties = additionalProperties,
            ContinuationToken = continuationToken,
            RawRepresentation = rawRepresentation
        };

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (m, session, options, cancellationToken) => Task.FromResult(new AgentResponse(innerChatResponse))
        };

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        // M.E.AI has no ChatResponse.Clone(), so the stamp is a hand-written member-wise copy. Every member
        // must survive it, and the inner client's own response must come back unmodified.
        Assert.NotSame(innerChatResponse, response);
        Assert.Null(innerChatResponse.ConversationId);
        Assert.Equal("adapter-conversation", response.ConversationId);
        Assert.Same(messages, response.Messages);
        Assert.Equal("response-id", response.ResponseId);
        Assert.Equal("model-id", response.ModelId);
        Assert.Equal(createdAt, response.CreatedAt);
        Assert.Equal(ChatFinishReason.Stop, response.FinishReason);
        Assert.Same(usage, response.Usage);
        Assert.Same(additionalProperties, response.AdditionalProperties);
        Assert.Same(continuationToken, response.ContinuationToken);
        Assert.Same(rawRepresentation, response.RawRepresentation);
    }

    [Fact]
    public void ChatResponse_SettableMembersMatchTheSyntheticStampCopySet()
    {
        // Arrange
        // Guards the hand-written copy above: if a future M.E.AI adds or removes a settable member, this
        // fails so the copy set is revisited rather than silently dropping data.
        string[] copied =
        [
            nameof(ChatResponse.AdditionalProperties),
            nameof(ChatResponse.ContinuationToken),
            nameof(ChatResponse.ConversationId),
            nameof(ChatResponse.CreatedAt),
            nameof(ChatResponse.FinishReason),
            nameof(ChatResponse.Messages),
            nameof(ChatResponse.ModelId),
            nameof(ChatResponse.RawRepresentation),
            nameof(ChatResponse.ResponseId),
            nameof(ChatResponse.Usage)
        ];

        // Act
        var settable = typeof(ChatResponse)
            .GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(property => property.GetSetMethod(nonPublic: false) is not null)
            .Select(property => property.Name)
            .OrderBy(name => name, StringComparer.Ordinal);

        // Assert
        Assert.Equal(copied.OrderBy(name => name, StringComparer.Ordinal), settable);
    }

    [Fact]
    public async Task GetResponseAsync_WithoutSession_ForwardsConversationIdUntouchedAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        var innerChatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "ok"))
        {
            ConversationId = "service-conversation"
        };

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedOptions = options;
                return Task.FromResult(new AgentResponse(innerChatResponse));
            }
        };

        using var chatClient = agent.AsIChatClient();
        var chatOptions = new ChatOptions { ConversationId = "caller-conversation" };

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions);

        // Assert
        // Stateless mode already conforms to the IChatClient contract, so no id machinery applies to it at
        // all: options go in verbatim and whatever id the response carries comes back verbatim.
        Assert.Same(chatOptions, Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions);
        Assert.Equal("caller-conversation", chatOptions.ConversationId);
        Assert.Same(innerChatResponse, response);
        Assert.Equal("service-conversation", response.ConversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithUnrecognizedRawConversationIds_ReportsAdapterIdAndAcceptsItBackAsync()
    {
        // Arrange
        // Nothing in this stream is session-backed: the session never learns an id, so the raw id appearing
        // mid-stream names a conversation the adapter could not honor on the next turn.
        ChatResponseUpdate[] rawUpdates =
        [
            new(ChatRole.Assistant, "one"),
            new(ChatRole.Assistant, "two"),
            new(ChatRole.Assistant, "three") { ConversationId = "svc-raw" },
            new(ChatRole.Assistant, "four")
        ];

        var agentUpdates = rawUpdates
            .Select(update => new AgentResponseUpdate(ChatRole.Assistant, update.Text) { RawRepresentation = update })
            .ToList();

        AgentRunOptions? capturedOptions = null;
        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedOptions = options;
                return ToAsyncEnumerableAsync(agentUpdates, cancellationToken);
            }
        };

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        var reportedConversationId = receivedUpdates.ToChatResponse().ConversationId;

        // Echo the reported id straight back, which is precisely what a protocol-conformant caller does.
        await foreach (var _ in chatClient.GetStreamingResponseAsync(
            [new ChatMessage(ChatRole.User, "Again")],
            new ChatOptions { ConversationId = reportedConversationId }))
        {
            // Enumerate to completion.
        }

        // Assert
        // Every update reports the adapter's id, on clones that leave the inner client's objects untouched.
        Assert.Equal(4, receivedUpdates.Count);
        Assert.All(receivedUpdates, update => Assert.Equal("adapter-conversation", update.ConversationId));
        for (var i = 0; i < receivedUpdates.Count; i++)
        {
            Assert.NotSame(rawUpdates[i], receivedUpdates[i]);
        }

        Assert.Null(rawUpdates[0].ConversationId);
        Assert.Equal("svc-raw", rawUpdates[2].ConversationId);

        // The round trip closes: what was reported is accepted back, and stripped rather than rejected.
        Assert.Equal("adapter-conversation", reportedConversationId);
        Assert.Null(Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions!.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithUnrecognizedRawConversationId_ReportsAdapterIdAndAcceptsItBackAsync()
    {
        // Arrange
        // The raw response names a conversation the session knows nothing about. Reporting it would be a trap:
        // the very next call would have to reject the id the adapter had just handed out.
        AgentRunOptions? capturedOptions = null;

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatResponse(new ChatMessage(ChatRole.Assistant, "ok"))
                {
                    ConversationId = "foreign-raw"
                }));
            }
        };

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");

        // Act
        var first = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);
        var second = await chatClient.GetResponseAsync(
            [new ChatMessage(ChatRole.User, "Again")],
            new ChatOptions { ConversationId = first.ConversationId });

        // Assert
        // Reported id is the adapter's own, and echoing it back is accepted and stripped rather than rejected.
        Assert.Equal("adapter-conversation", first.ConversationId);
        Assert.Equal("adapter-conversation", second.ConversationId);
        Assert.Null(Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions!.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithConversationIdMatchingAdapterAndServiceId_ForwardsOptionsUntouchedAsync()
    {
        // Arrange
        // A developer may hand the adapter the very id the service uses. The known-service-id check runs first, so
        // the id reaches ChatClientAgent for its own session validation instead of being silently stripped.
        AgentRunOptions? capturedOptions = null;

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            }
        };

        var session = new ChatClientAgentSession("shared-conversation");
        using var chatClient = agent.AsIChatClient(session, "shared-conversation");
        var chatOptions = new ChatOptions { ConversationId = "shared-conversation" };

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions);

        // Assert
        Assert.Same(chatOptions, Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions);
    }

    [Fact]
    public async Task GetResponseAsync_OverAgentPersistingHistoryPerServiceCall_NeverReportsLocalHistorySentinelAsync()
    {
        // Arrange
        // With RequirePerServiceCallChatHistoryPersistence the pipeline stamps a sentinel conversation id on both the
        // response and the session to tell FunctionInvokingChatClient that history is handled downstream. It names no
        // resumable conversation, so it must never surface as this adapter's reported id.
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service.")));

        var agent = new ChatClientAgent(
            mockChatClient.Object,
            new ChatClientAgentOptions { RequirePerServiceCallChatHistoryPersistence = true });

        var suppliedIdSession = await agent.CreateSessionAsync();
        var generatedIdSession = await agent.CreateSessionAsync();

        using var suppliedIdChatClient = agent.AsIChatClient(suppliedIdSession, "dev-conversation");
        using var generatedIdChatClient = agent.AsIChatClient(generatedIdSession);

        // Act
        var suppliedIdResponse = await suppliedIdChatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);
        var generatedIdResponse = await generatedIdChatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.Equal(
            PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId,
            suppliedIdSession.GetService<ChatClientAgentSession>()!.ConversationId);

        Assert.Equal("dev-conversation", suppliedIdResponse.ConversationId);
        Assert.NotNull(generatedIdResponse.ConversationId);
        Assert.NotEqual(
            PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId,
            generatedIdResponse.ConversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_OverAgentPersistingHistoryPerServiceCall_NeverReportsLocalHistorySentinelAsync()
    {
        // Arrange
        // The streaming half of the same trap: the decorator stamps the sentinel on every update, which would
        // otherwise read as "a real id appeared" and stop the adapter synthesizing.
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
            .Returns<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>(
                (_, _, ct) => ToAsyncEnumerableAsync(serviceUpdates.ConvertAll(u => u.Clone()), ct));

        var agent = new ChatClientAgent(
            mockChatClient.Object,
            new ChatClientAgentOptions { RequirePerServiceCallChatHistoryPersistence = true });

        var session = await agent.CreateSessionAsync();
        using var chatClient = agent.AsIChatClient(session, "dev-conversation");

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        Assert.NotEmpty(receivedUpdates);
        Assert.All(receivedUpdates, update => Assert.Equal("dev-conversation", update.ConversationId));
        Assert.Equal("dev-conversation", receivedUpdates.ToChatResponse().ConversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithSessionKnowingServiceConversationId_ReportsThatIdOnEveryUpdateAsync()
    {
        // Arrange
        // The session stands behind "known-service-conversation". An update already carrying it is passed through;
        // one carrying nothing, or an id the session does not know, is rewritten to the id the session backs.
        ChatResponseUpdate[] rawUpdates =
        [
            new(ChatRole.Assistant, "one") { ConversationId = "known-service-conversation" },
            new(ChatRole.Assistant, "two"),
            new(ChatRole.Assistant, "three") { ConversationId = "some-other-conversation" }
        ];

        var agentUpdates = rawUpdates
            .Select(update => new AgentResponseUpdate(ChatRole.Assistant, update.Text) { RawRepresentation = update })
            .ToList();

        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
                ToAsyncEnumerableAsync(agentUpdates, cancellationToken)
        };

        var session = new ChatClientAgentSession("known-service-conversation");
        using var chatClient = agent.AsIChatClient(session, "adapter-conversation");

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        Assert.Equal(3, receivedUpdates.Count);

        // Session-backed id, so no copy is made at all.
        Assert.Same(rawUpdates[0], receivedUpdates[0]);

        // The other two are rewritten on clones, leaving the inner client's objects untouched.
        Assert.NotSame(rawUpdates[1], receivedUpdates[1]);
        Assert.NotSame(rawUpdates[2], receivedUpdates[2]);
        Assert.Null(rawUpdates[1].ConversationId);
        Assert.Equal("some-other-conversation", rawUpdates[2].ConversationId);

        Assert.All(receivedUpdates, update => Assert.Equal("known-service-conversation", update.ConversationId));
        Assert.Equal("known-service-conversation", receivedUpdates.ToChatResponse().ConversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithEchoedAdapterConversationId_StripsItBeforeTheAgentSeesItAsync()
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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");
        var chatOptions = new ChatOptions { ConversationId = "adapter-conversation", Temperature = 0.25f };

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions))
        {
            // Enumerate to completion.
        }

        // Assert
        // Same request-side contract as the non-streaming path, including leaving the caller's options untouched.
        var forwarded = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions;
        Assert.NotNull(forwarded);
        Assert.NotSame(chatOptions, forwarded);
        Assert.Null(forwarded!.ConversationId);
        Assert.Equal(0.25f, forwarded.Temperature);
        Assert.Equal("adapter-conversation", chatOptions.ConversationId);
    }

    [Fact]
    public void GetStreamingResponseAsync_WithForeignConversationId_ThrowsSynchronously()
    {
        // Arrange
        var agent = new TestAIAgent();
        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");

        // Act & Assert
        // The rejection must come from the call itself, not from enumerating the result, which is only true
        // because the entry point is not an iterator. Nothing here enumerates the returned sequence.
        var exception = Assert.Throws<InvalidOperationException>(
            (Action)(() => chatClient.GetStreamingResponseAsync(
                [new ChatMessage(ChatRole.User, "Hi")],
                new ChatOptions { ConversationId = "someone-elses-conversation" })));

        Assert.Contains("AsIChatClient", exception.Message, StringComparison.Ordinal);
        Assert.Contains("CreateSessionAsync", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WhenSessionLearnsServiceIdMidRun_ReportsItFromThatPointAndRoundTripsAsync()
    {
        // Arrange
        // The session starts with no id and adopts "S" part-way through the stream, exactly as a service-managed run
        // does: the agent records the id on the session, but only once its own update loop has moved on.
        var session = new ChatClientAgentSession();
        AgentRunOptions? capturedOptions = null;

        async IAsyncEnumerable<AgentResponseUpdate> StreamAsync()
        {
            yield return new(ChatRole.Assistant, "before");
            await Task.Yield();

            session.ConversationId = "S";

            yield return new(ChatRole.Assistant, "after")
            {
                RawRepresentation = new ChatResponseUpdate(ChatRole.Assistant, "after") { ConversationId = "S" }
            };
        }

        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, s, options, cancellationToken) =>
            {
                capturedOptions = options;
                return StreamAsync();
            }
        };

        using var chatClient = agent.AsIChatClient(session, "adapter-conversation");

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        var reportedConversationId = receivedUpdates.ToChatResponse().ConversationId;

        // Echo back whatever was reported, which is all a protocol-conformant caller knows to do.
        await foreach (var _ in chatClient.GetStreamingResponseAsync(
            [new ChatMessage(ChatRole.User, "Again")],
            new ChatOptions { ConversationId = reportedConversationId }))
        {
            // Enumerate to completion.
        }

        // Assert
        Assert.Equal(2, receivedUpdates.Count);
        Assert.Equal("adapter-conversation", receivedUpdates[0].ConversationId);
        Assert.Equal("S", receivedUpdates[1].ConversationId);
        Assert.Equal("S", reportedConversationId);

        // The echo is accepted rather than rejected. By the second call the session holds "S" itself, so the id is
        // forwarded for ChatClientAgent to validate rather than stripped; either outcome names the same conversation.
        var forwarded = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions;
        Assert.True(
            forwarded!.ConversationId is null || forwarded.ConversationId == "S",
            $"Expected the echoed id to be stripped or forwarded as the current conversation, got '{forwarded.ConversationId}'.");
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WhenServiceAdvancesConversationIdMidRun_ReportedIdIsStillAcceptedAsync()
    {
        // Arrange
        // A forking service mints a new id every turn: the stream carries "S2" while the session still holds "S1",
        // and the session only catches up as the run ends. Whatever the caller is handed must remain usable, or the
        // very next turn fails on an id this adapter itself produced.
        var session = new ChatClientAgentSession("S1");
        AgentRunOptions? capturedOptions = null;

        async IAsyncEnumerable<AgentResponseUpdate> StreamAsync()
        {
            yield return new(ChatRole.Assistant, "chunk")
            {
                RawRepresentation = new ChatResponseUpdate(ChatRole.Assistant, "chunk") { ConversationId = "S2" }
            };

            await Task.Yield();

            // End of run: the session adopts the new id, superseding whatever was already streamed.
            session.ConversationId = "S2";
        }

        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, s, options, cancellationToken) =>
            {
                capturedOptions = options;
                return StreamAsync();
            }
        };

        using var chatClient = agent.AsIChatClient(session, "adapter-conversation");

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        var reportedConversationId = receivedUpdates.ToChatResponse().ConversationId;

        // Assert
        // The reported id must round-trip. It is stale by now — the session moved to "S2" only after it was
        // streamed — so acceptance cannot be decided from the session's current value alone.
        Assert.NotNull(reportedConversationId);

        await foreach (var _ in chatClient.GetStreamingResponseAsync(
            [new ChatMessage(ChatRole.User, "Again")],
            new ChatOptions { ConversationId = reportedConversationId }))
        {
            // Enumerate to completion; the absence of an InvalidOperationException is the assertion.
        }

        var forwarded = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions;
        Assert.True(
            forwarded!.ConversationId is null || forwarded.ConversationId == "S2",
            $"Expected the echoed id to be stripped or resolved to the current conversation, got '{forwarded.ConversationId}'.");
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithBoundSessionAndEmptyStream_ReportsConversationIdAnywayAsync()
    {
        // Arrange
        // A run that yields nothing would otherwise aggregate to a null conversation id, which the IChatClient
        // contract reads as "no stored history" — inviting the caller to resend everything into a session that is
        // already accumulating it.
        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
                ToAsyncEnumerableAsync<AgentResponseUpdate>([], cancellationToken)
        };

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        var trailing = Assert.Single(receivedUpdates);
        Assert.Equal("adapter-conversation", trailing.ConversationId);

        // The aggregate shape is deliberate: one empty assistant message carrying the id, rather than an empty
        // message list, so that the id survives aggregation at all.
        var aggregated = receivedUpdates.ToChatResponse();
        Assert.Equal("adapter-conversation", aggregated.ConversationId);
        var message = Assert.Single(aggregated.Messages);
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Empty(message.Contents);
        Assert.Equal(string.Empty, message.Text);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithoutSessionAndEmptyStream_YieldsNothingAsync()
    {
        // Arrange
        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
                ToAsyncEnumerableAsync<AgentResponseUpdate>([], cancellationToken)
        };

        using var chatClient = agent.AsIChatClient();

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        // Stateless mode stores nothing, so there is no conversation to announce and nothing is invented.
        Assert.Empty(receivedUpdates);
    }

    [Fact]
    public async Task GetResponseAsync_WithNonChatClientAgentSession_ReportsAdapterIdAsync()
    {
        // Arrange
        // The service-id probe recognizes ChatClientAgentSession only. Any other session type falls back to the
        // adapter's own id, which is the documented limitation.
        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
                Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")))
        };

        using var chatClient = agent.AsIChatClient(new UnrecognizedAgentSession(), "adapter-conversation");

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.Equal("adapter-conversation", response.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithReservedConversationIdInOptions_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        // RunAsyncFunc is left at its throwing default: the sentinel names no resumable conversation, so it must be
        // rejected like any other unrecognized id rather than reaching the agent.
        var agent = new TestAIAgent();
        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation");

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            chatClient.GetResponseAsync(
                [new ChatMessage(ChatRole.User, "Hi")],
                new ChatOptions { ConversationId = PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId }));

        Assert.Contains("AsIChatClient", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetResponseAsync_WithForeignConversationId_DoesNotDiscloseAcceptedIdsAsync()
    {
        // Arrange
        // The message can reach an untrusted caller through a host, so it must not turn into an oracle for live
        // conversation ids.
        var agent = new TestAIAgent();
        var session = new ChatClientAgentSession("secret-service-conversation");
        using var chatClient = agent.AsIChatClient(session, "secret-adapter-conversation");

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            chatClient.GetResponseAsync(
                [new ChatMessage(ChatRole.User, "Hi")],
                new ChatOptions { ConversationId = "probe" }));

        Assert.Contains("probe", exception.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("secret-service-conversation", exception.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("secret-adapter-conversation", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ToChatResponseAsync_ResolvesConversationIdAsLastNonNullWinsAsync()
    {
        // Arrange
        // Premise check for the streaming design above. Aggregation keeps the last non-null id it saw, which is why
        // every update must carry the id the adapter intends to report: leaving even one trailing update with a
        // foreign id would let that id win the aggregate and be handed to a caller who cannot use it.
        List<ChatResponseUpdate> updates =
        [
            new(ChatRole.Assistant, "a") { ConversationId = "first" },
            new(ChatRole.Assistant, "b"),
            new(ChatRole.Assistant, "c") { ConversationId = "second" },
            new(ChatRole.Assistant, "d")
        ];

        // Act
        var response = await ToAsyncEnumerableAsync(updates).ToChatResponseAsync();

        // Assert
        Assert.Equal("second", response.ConversationId);
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
    /// An <see cref="AgentSession"/> that is not a <see cref="ChatClientAgentSession"/>, used to exercise the
    /// documented fallback for session types whose service conversation id the adapter cannot read.
    /// </summary>
    private sealed class UnrecognizedAgentSession : AgentSession;

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
