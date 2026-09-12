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
    public void AsIChatClient_WithAgentNotExposingChatClientAgent_ThrowsInvalidOperationException()
    {
        // Arrange
        var agent = new TestAIAgent();

        // Act & Assert
        // An agent that does not understand ChatClientAgentRunOptions would silently drop nearly every ChatOptions
        // member a caller supplies, so wrapping it is refused unless the caller says it knows.
        var exception = Assert.Throws<InvalidOperationException>(() => agent.AsIChatClient());

        Assert.Contains(nameof(TestAIAgent), exception.Message, StringComparison.Ordinal);
        Assert.Contains("allowNonChatClientAgents", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AsIChatClient_WithOptIn_ReturnsChatClient()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();

        // Act
        using var chatClient = mockAgent.Object.AsIChatClient(allowNonChatClientAgents: true);

        // Assert
        Assert.NotNull(chatClient);
    }

    [Fact]
    public void AsIChatClient_WithOptIn_DoesNotProbeAgentForChatClientAgent()
    {
        // Arrange
        // The opt-in short-circuits the capability check, so the agent must never be asked anything. Tests that count
        // GetService requests rely on this, and so do agents whose GetService is expensive or has side effects.
        var agent = new TestAIAgent
        {
            GetServiceFunc = (_, _) => throw new InvalidOperationException("must not be called")
        };

        // Act
        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

        // Assert
        // The assertion that matters is that the Act did not throw: a GetService request would have.
        Assert.NotNull(chatClient);
    }

    [Fact]
    public void AsIChatClient_OverChatClientAgent_DoesNotRequireOptIn()
    {
        // Arrange
        var agent = new ChatClientAgent(new Mock<IChatClient>().Object);

        // Act
        using var chatClient = agent.AsIChatClient();

        // Assert
        // The assertion that matters is that the Act did not throw: without the opt-in, a rejected agent would have.
        Assert.NotNull(chatClient);
    }

    [Fact]
    public void AsIChatClient_OverDelegatingAgentWrappingChatClientAgent_DoesNotRequireOptIn()
    {
        // Arrange
        // DelegatingAIAgent forwards GetService to the agent it wraps, so a middleware pipeline over a
        // ChatClientAgent still honors ChatClientAgentRunOptions and needs no opt-in.
        var agent = new ChatClientAgent(new Mock<IChatClient>().Object)
            .AsBuilder()
            .Use(async (messages, session, options, next, cancellationToken) =>
                await next(messages, session, options, cancellationToken))
            .Build();

        // Act
        using var chatClient = agent.AsIChatClient();

        // Assert
        // The assertion that matters is that the Act did not throw: without the opt-in, a rejected agent would have.
        Assert.NotNull(chatClient);
    }

    [Fact]
    public void AsIChatClient_OverDelegatingAgentWrappingNonChatClientAgent_ThrowsInvalidOperationException()
    {
        // Arrange
        // The same pipeline over an agent that is not a ChatClientAgent forwards the probe and finds nothing.
        var agent = new TestAIAgent()
            .AsBuilder()
            .Use(async (messages, session, options, next, cancellationToken) =>
                await next(messages, session, options, cancellationToken))
            .Build();

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => agent.AsIChatClient());

        Assert.Contains("allowNonChatClientAgents", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AsIChatClient_OverAgentExposingChatClientAgentViaGetService_DoesNotRequireOptIn()
    {
        // Arrange
        var innerAgent = new ChatClientAgent(new Mock<IChatClient>().Object);
        List<(Type ServiceType, object? ServiceKey)> capturedRequests = [];

        var agent = new TestAIAgent
        {
            GetServiceFunc = (serviceType, serviceKey) =>
            {
                capturedRequests.Add((serviceType, serviceKey));
                return serviceType == typeof(ChatClientAgent) ? innerAgent : null;
            }
        };

        // Act
        using var chatClient = agent.AsIChatClient();

        // Assert
        Assert.NotNull(chatClient);

        // The probe is unkeyed, so an agent that only answers keyed requests is not mistaken for one that honors
        // ChatClientAgentRunOptions.
        Assert.Equal((typeof(ChatClientAgent), null), Assert.Single(capturedRequests));
    }

    [Fact]
    public void AsIChatClient_OverAgentExposingOnlyChatClient_RequiresOptIn()
    {
        // Arrange
        // The capability that matters is honoring ChatClientAgentRunOptions, not owning an IChatClient, so an agent
        // that hands out its inner chat client but is not a ChatClientAgent is still rejected.
        var chatClient = new Mock<IChatClient>().Object;
        var agent = new TestAIAgent
        {
            GetServiceFunc = (serviceType, _) => serviceType == typeof(IChatClient) ? chatClient : null
        };

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => agent.AsIChatClient());

        Assert.Contains("allowNonChatClientAgents", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AsIChatClient_WithInvalidConversationIdAndUnsupportedAgent_ThrowsArgumentException()
    {
        // Arrange
        var agent = new TestAIAgent();

        // Act & Assert
        // Argument validation runs before the capability check, so a caller who got both wrong is told about the
        // argument first rather than being sent to fix the opt-in and then hitting the same wall again.
        var exception = Assert.Throws<ArgumentException>(() =>
            agent.AsIChatClient(session: null, conversationId: "orphan"));

        Assert.Equal("conversationId", exception.ParamName);
    }

    [Fact]
    public async Task GetResponseAsync_WithNullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        using var chatClient = mockAgent.Object.AsIChatClient(allowNonChatClientAgents: true);

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
        using var chatClient = mockAgent.Object.AsIChatClient(allowNonChatClientAgents: true);

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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);
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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);
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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);
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

        using var chatClient = agent.AsIChatClient(boundSession, allowNonChatClientAgents: true);

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.Same(boundSession, capturedSession);
    }

    [Fact]
    public async Task GetResponseAsync_WithChatResponseRawRepresentation_ReturnsSameInstanceAsync()
    {
        // Arrange
        // No conversation id: a stateless client clears one that is present, so the instance is only returned as it
        // stands when there is nothing to clear.
        var innerChatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Hello"))
        {
            ResponseId = "response-42"
        };

        var agentResponse = new AgentResponse(innerChatResponse);

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) => Task.FromResult(agentResponse)
        };

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.Same(innerChatResponse, response);
        Assert.Null(response.ConversationId);
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

        using var chatClient = agent.AsIChatClient(boundSession, allowNonChatClientAgents: true);
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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);
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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);
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
        using var chatClient = mockAgent.Object.AsIChatClient(allowNonChatClientAgents: true);

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
        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

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
        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

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

        // The opt-in short-circuits the ChatClientAgent capability probe, so the only requests counted below are
        // the ones this test makes.
        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

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

        var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

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
                Tools = [requestTool]
            });

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equal("agent instructions\nrequest instructions", capturedChatOptions!.Instructions);
        Assert.NotNull(capturedChatOptions.Tools);
        Assert.Contains(capturedChatOptions.Tools!, t => t.Name == "AgentTool");
        Assert.Contains(capturedChatOptions.Tools!, t => t.Name == "RequestTool");

        Assert.Equal("Response from the service.", response.Text);
        Assert.Null(response.ConversationId);
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
            agent.AsIChatClient(session: null, conversationId: "orphan-conversation", allowNonChatClientAgents: true));

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
            agent.AsIChatClient(new ChatClientAgentSession(), conversationId, allowNonChatClientAgents: true));

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
                PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId,
                allowNonChatClientAgents: true));

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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), allowNonChatClientAgents: true);
        using var otherChatClient = agent.AsIChatClient(new ChatClientAgentSession(), allowNonChatClientAgents: true);

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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "my-own-conversation-id", allowNonChatClientAgents: true);

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        Assert.Equal("my-own-conversation-id", response.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithBoundSessionAndServiceManagedResponse_ReturnsStampedCloneAsync()
    {
        // Arrange
        var serviceRawRepresentation = new object();
        var innerChatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Hello"))
        {
            ConversationId = "service-conversation",
            RawRepresentation = serviceRawRepresentation
        };

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) => Task.FromResult(new AgentResponse(innerChatResponse))
        };

        var session = new ChatClientAgentSession("service-conversation");
        using var chatClient = agent.AsIChatClient(session, "adapter-conversation", allowNonChatClientAgents: true);

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        // In bound mode the client reports its own id and nothing else, so even a real service id is replaced. The
        // replacement happens on a copy, so the inner client's own response is left unmodified and the copy shares
        // its RawRepresentation member rather than dropping it.
        Assert.NotSame(innerChatResponse, response);
        Assert.Equal("adapter-conversation", response.ConversationId);
        Assert.Equal("service-conversation", innerChatResponse.ConversationId);
        Assert.Same(serviceRawRepresentation, response.RawRepresentation);
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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);
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
    public async Task GetResponseAsync_WithEchoedServiceConversationId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        // RunAsyncFunc is left at its throwing default: the request must be rejected before it reaches the agent.
        var agent = new TestAIAgent();

        var session = new ChatClientAgentSession("known-service-conversation");
        using var chatClient = agent.AsIChatClient(session, "adapter-conversation", allowNonChatClientAgents: true);

        // Act & Assert
        // The bound client never reports the session's service id, so it does not accept it either. Only the id it
        // hands out is a known id; anything else, however real, is not this client's to serve.
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            chatClient.GetResponseAsync(
                [new ChatMessage(ChatRole.User, "Hi")],
                new ChatOptions { ConversationId = "known-service-conversation" }));

        Assert.Contains("AsIChatClient", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetResponseAsync_WithForeignConversationId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        // RunAsyncFunc is left at its throwing default: the request must be rejected before it reaches the agent.
        var agent = new TestAIAgent();
        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);

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

        using var chatClient = agent.AsIChatClient(boundSession, allowNonChatClientAgents: true);

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Again")], new ChatOptions());

        // Assert
        // A fixed bound session cannot fork, so an absent id means "keep going" rather than "start fresh".
        Assert.Equal(2, capturedSessions.Count);
        Assert.All(capturedSessions, session => Assert.Same(boundSession, session));
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public async Task GetResponseAsync_WithBoundSessionAndBlankConversationId_ReusesBoundSessionAsync(string conversationId)
    {
        // Arrange
        // Transports routinely turn an omitted field into an empty string. A blank id names no conversation, so it
        // must read as absent; treating it as unknown would reject the caller for doing exactly what the rejection
        // message tells them to do — omit the id.
        AgentSession? capturedSession = null;
        AgentRunOptions? capturedOptions = null;

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedSession = session;
                capturedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            }
        };

        var boundSession = new ChatClientAgentSession();
        using var chatClient = agent.AsIChatClient(boundSession, "adapter-conversation", allowNonChatClientAgents: true);
        var chatOptions = new ChatOptions { ConversationId = conversationId };

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions);

        // Assert
        // The run proceeds against the bound session, and the blank id is cleared on a copy so that nothing
        // downstream can read it as naming a conversation. The caller's own instance is left as it was.
        Assert.Same(boundSession, capturedSession);

        var forwarded = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions;
        Assert.NotSame(chatOptions, forwarded);
        Assert.Null(forwarded!.ConversationId);
        Assert.Equal(conversationId, chatOptions.ConversationId);
        Assert.Equal("adapter-conversation", response.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WhenStampingConversationId_PreservesEveryResponseMemberAsync()
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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);

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
    public void ChatResponse_SettableMembersMatchTheConversationIdStampCopySet()
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
    public async Task GetResponseAsync_WithoutSessionAndConversationId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        // RunAsyncFunc is left at its throwing default: reaching the agent at all would fail the test differently,
        // which pins that the rejection happens before the run rather than after it.
        var agent = new TestAIAgent();

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

        // Act & Assert
        // A stateless client hands out no conversation id, so there is none it can take back. Forwarding one would let
        // a caller name a service-side conversation the host never offered it.
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            chatClient.GetResponseAsync(
                [new ChatMessage(ChatRole.User, "Hi")],
                new ChatOptions { ConversationId = "caller-conversation" }));

        // "not bound to a session" separates this from the bound rejection, and the caller's own value is named
        // because there is nothing to withhold: a stateless client accepts no id, so no accepted id can leak.
        Assert.Contains("not bound to a session", exception.Message, StringComparison.Ordinal);
        Assert.Contains("caller-conversation", exception.Message, StringComparison.Ordinal);
        Assert.Contains("AsIChatClient", exception.Message, StringComparison.Ordinal);
        Assert.Contains("CreateSessionAsync", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void GetStreamingResponseAsync_WithoutSessionAndConversationId_ThrowsSynchronously()
    {
        // Arrange
        var agent = new TestAIAgent();
        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

        // Act & Assert
        // As in bound mode, the rejection must come from the call itself rather than from enumerating the result.
        // Nothing here enumerates the returned sequence.
        var exception = Assert.Throws<InvalidOperationException>(
            (Action)(() => chatClient.GetStreamingResponseAsync(
                [new ChatMessage(ChatRole.User, "Hi")],
                new ChatOptions { ConversationId = "caller-conversation" })));

        Assert.Contains("not bound to a session", exception.Message, StringComparison.Ordinal);
        Assert.Contains("caller-conversation", exception.Message, StringComparison.Ordinal);
        Assert.Contains("AsIChatClient", exception.Message, StringComparison.Ordinal);
        Assert.Contains("CreateSessionAsync", exception.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public async Task GetResponseAsync_WithoutSessionAndBlankConversationId_NormalizesItToAbsentOnACloneAsync(string conversationId)
    {
        // Arrange
        // Transports routinely materialize an omitted field as an empty string, so a blank id means "none given"
        // rather than "unknown conversation" and must not trip the rejection.
        AgentRunOptions? capturedOptions = null;

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
            }
        };

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);
        var chatOptions = new ChatOptions { ConversationId = conversationId };

        // Act
        await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions);

        // Assert
        // Forwarding the blank value as it stands would not be harmless: downstream blankness checks use
        // IsNullOrEmpty, so whitespace would be read as naming a service-managed conversation, and an empty string
        // would suppress the id the agent is configured with. It is cleared on a copy, leaving the caller's instance.
        var forwarded = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions;
        Assert.NotSame(chatOptions, forwarded);
        Assert.Null(forwarded!.ConversationId);
        Assert.Equal(conversationId, chatOptions.ConversationId);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public async Task GetStreamingResponseAsync_WithoutSessionAndBlankConversationId_NormalizesItToAbsentOnACloneAsync(string conversationId)
    {
        // Arrange
        // Both entry points resolve options through the same path, so the streaming half of the matrix must agree.
        AgentRunOptions? capturedOptions = null;

        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
            {
                capturedOptions = options;
                return ToAsyncEnumerableAsync<AgentResponseUpdate>([new(ChatRole.Assistant, "ok")], cancellationToken);
            }
        };

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);
        var chatOptions = new ChatOptions { ConversationId = conversationId };

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")], chatOptions))
        {
            // Enumerate to completion.
        }

        // Assert
        var forwarded = Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions;
        Assert.NotSame(chatOptions, forwarded);
        Assert.Null(forwarded!.ConversationId);
        Assert.Equal(conversationId, chatOptions.ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithoutSessionAndRawConversationId_ReturnsCloneWithoutConversationIdAsync()
    {
        // Arrange
        var rawRepresentation = new object();
        var innerChatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "ok"))
        {
            ConversationId = "service-conversation",
            RawRepresentation = rawRepresentation,
            ResponseId = "response-42"
        };

        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
                Task.FromResult(new AgentResponse(innerChatResponse))
        };

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        // A stateless client reports no conversation id, so a service id riding on the raw response is cleared. The
        // response belongs to the inner client, so the clearing happens on a copy that keeps everything else.
        Assert.Null(response.ConversationId);
        Assert.NotSame(innerChatResponse, response);
        Assert.Same(rawRepresentation, response.RawRepresentation);
        Assert.Equal("response-42", response.ResponseId);
        Assert.Equal("service-conversation", innerChatResponse.ConversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithoutSessionAndRawConversationIds_ClearsThemOnClonesAsync()
    {
        // Arrange
        // The streaming half: ids may appear on any subset of the updates, and none of them may reach the caller.
        ChatResponseUpdate[] rawUpdates =
        [
            new(ChatRole.Assistant, "one"),
            new(ChatRole.Assistant, "two") { ConversationId = "svc-raw" },
            new(ChatRole.Assistant, "three"),
            new(ChatRole.Assistant, "four") { ConversationId = "svc-raw-again" }
        ];

        var agentUpdates = rawUpdates
            .Select(update => new AgentResponseUpdate(ChatRole.Assistant, update.Text) { RawRepresentation = update })
            .ToList();

        var agent = new TestAIAgent
        {
            RunStreamingAsyncFunc = (messages, session, options, cancellationToken) =>
                ToAsyncEnumerableAsync(agentUpdates, cancellationToken)
        };

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        Assert.Equal(4, receivedUpdates.Count);
        Assert.All(receivedUpdates, update => Assert.Null(update.ConversationId));

        // An update that carried an id is copied before being cleared; one that carried none is passed straight
        // through, which is the identity guarantee the raw-representation tests rely on.
        Assert.Same(rawUpdates[0], receivedUpdates[0]);
        Assert.NotSame(rawUpdates[1], receivedUpdates[1]);
        Assert.Same(rawUpdates[2], receivedUpdates[2]);
        Assert.NotSame(rawUpdates[3], receivedUpdates[3]);

        // The inner client's own updates are untouched.
        Assert.Equal("svc-raw", rawUpdates[1].ConversationId);
        Assert.Equal("svc-raw-again", rawUpdates[3].ConversationId);

        Assert.Null(receivedUpdates.ToChatResponse().ConversationId);
    }

    [Fact]
    public async Task GetResponseAsync_WithoutSessionOverServiceManagedChatClientAgent_ReportsNoConversationIdAndStartsFreshEachCallAsync()
    {
        // Arrange
        // A genuinely service-managed pipeline: the inner client mints a real conversation id on every call.
        List<string?> innerConversationIds = [];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) => innerConversationIds.Add(options?.ConversationId))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service."))
            {
                ConversationId = "svc"
            });

        var agent = new ChatClientAgent(mockChatClient.Object);

        using var chatClient = agent.AsIChatClient();

        // Act
        var first = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);
        var second = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Again")]);

        // Assert
        // The service id exists and is simply never reported, so the caller is never handed an id this client would
        // refuse on the next call. With no session to continue, each call starts from the history it was given.
        Assert.Null(first.ConversationId);
        Assert.Null(second.ConversationId);
        Assert.Equal(2, innerConversationIds.Count);
        Assert.All(innerConversationIds, id => Assert.Null(id));
    }

    [Fact]
    public async Task GetResponseAsync_WithoutSessionOverServiceManagedChatClientAgentAndConversationId_ThrowsBeforeRunningAsync()
    {
        // Arrange
        // The attack this closes: naming the service's own conversation and having the agent read and extend it
        // under the host's credentials. The service id is a real one here, and it is still refused.
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service."))
            {
                ConversationId = "svc"
            });

        var agent = new ChatClientAgent(mockChatClient.Object);

        using var chatClient = agent.AsIChatClient();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            chatClient.GetResponseAsync(
                [new ChatMessage(ChatRole.User, "Hi")],
                new ChatOptions { ConversationId = "svc" }));

        Assert.Contains("AsIChatClient", exception.Message, StringComparison.Ordinal);

        mockChatClient.Verify(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never());
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithUnrecognizedRawConversationIds_ReportsAdapterIdAndAcceptsItBackAsync()
    {
        // Arrange
        // A raw service id appears mid-stream. It must not leak through: the client reports only the id it was
        // configured with, so the id it hands out on this turn is one it still accepts on the next.
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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);

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
        // The raw response carries a service id. Forwarding it would be a trap: the client accepts only the id it
        // reports, so the very next call would have to reject an id it had just handed out.
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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);

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

    [Theory]
    [InlineData("dev-conversation")]
    [InlineData(null)]
    public async Task GetResponseAsync_OverServiceManagedChatClientAgent_ReportsConfiguredIdNotServiceIdAsync(string? conversationId)
    {
        // Arrange
        // A genuinely service-managed pipeline: the inner client returns a real conversation id and ChatClientAgent
        // records it on the session. The bound client still reports only its own id.
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service."))
            {
                ConversationId = "svc"
            });

        var agent = new ChatClientAgent(mockChatClient.Object);
        var session = await agent.CreateSessionAsync();

        using var chatClient = agent.AsIChatClient(session, conversationId);

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Assert
        // The session really did learn "svc" — the service id exists and is simply not what gets reported.
        Assert.Equal("svc", session.GetService<ChatClientAgentSession>()!.ConversationId);
        Assert.NotEqual("svc", response.ConversationId);
        Assert.NotNull(response.ConversationId);

        if (conversationId is not null)
        {
            Assert.Equal(conversationId, response.ConversationId);
        }
    }

    [Fact]
    public async Task GetResponseAsync_OverServiceManagedChatClientAgent_ContinuesTheServiceConversationAcrossTurnsAsync()
    {
        // Arrange
        // The end-to-end claim: the caller only ever sees the configured id, yet the service conversation is still
        // continued correctly underneath. Turn 2 echoes the reported id; the client strips it to null, which is what
        // lets ChatClientAgent re-apply the session's real id on the way down to the service.
        List<string?> innerConversationIds = [];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) => innerConversationIds.Add(options?.ConversationId))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service."))
            {
                ConversationId = "svc"
            });

        var agent = new ChatClientAgent(mockChatClient.Object);
        var session = await agent.CreateSessionAsync();

        using var chatClient = agent.AsIChatClient(session, "dev-conversation");

        // Act
        var first = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);
        var second = await chatClient.GetResponseAsync(
            [new ChatMessage(ChatRole.User, "Again")],
            new ChatOptions { ConversationId = first.ConversationId });

        // Assert
        // Turn 1: the session learned the real id, the caller was told the configured one.
        Assert.Equal("svc", session.GetService<ChatClientAgentSession>()!.ConversationId);
        Assert.Equal("dev-conversation", first.ConversationId);
        Assert.Equal("dev-conversation", second.ConversationId);

        // Turn 2: the service was addressed with its own conversation, not with the id the caller echoed.
        Assert.Equal(2, innerConversationIds.Count);
        Assert.Null(innerConversationIds[0]);
        Assert.Equal("svc", innerConversationIds[1]);
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
        // The streaming half of the same trap: the decorator stamps the sentinel on every update, so an id does
        // reach this client on every one of them. It is replaced, like any other incoming id.
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
    public async Task GetResponseAsync_WithoutSessionOverAgentPersistingHistoryPerServiceCall_NeverReportsLocalHistorySentinelAsync()
    {
        // Arrange
        // The sentinel names no resumable conversation; it tells FunctionInvokingChatClient that history is handled
        // downstream. Reporting it would hand the caller an id this client refuses on the very next call.
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

        using var chatClient = agent.AsIChatClient();

        // Act
        var response = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hi")]);

        // Premise check: the pipeline really does stamp the sentinel, so a client that forwarded ids would leak it.
        var direct = (await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")])).AsChatResponse();

        // Assert
        Assert.Equal(PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId, direct.ConversationId);
        Assert.Null(response.ConversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithoutSessionOverAgentPersistingHistoryPerServiceCall_NeverReportsLocalHistorySentinelAsync()
    {
        // Arrange
        // The streaming half of the same trap: the decorator stamps the sentinel on every update, so an id does reach
        // this client on each one. Statelessly every one of them is cleared.
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

        using var chatClient = agent.AsIChatClient();

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Premise check: the pipeline really does stamp the sentinel on every update, so a client that forwarded ids
        // would leak it.
        List<ChatResponseUpdate> directUpdates = [];
        await foreach (var update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            directUpdates.Add(update.AsChatResponseUpdate());
        }

        // Assert
        Assert.NotEmpty(directUpdates);
        Assert.All(
            directUpdates,
            update => Assert.Equal(
                PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId,
                update.ConversationId));

        Assert.NotEmpty(receivedUpdates);
        Assert.All(receivedUpdates, update => Assert.Null(update.ConversationId));
        Assert.Null(receivedUpdates.ToChatResponse().ConversationId);
    }

    [Fact]
    public async Task AsAIAgent_OverStatelessClient_RunsTwoTurnsWithoutRejectingTheRawIdAsync()
    {
        // Arrange
        // The round trip that makes the clearing rule load-bearing. ChatClientAgent's own session records whatever
        // conversation id the client below it reported and sends it back on the next turn. A stateless client reports
        // none, so there is nothing to echo and nothing for it to reject.
        List<string?> innerConversationIds = [];
        List<int> innerMessageCounts = [];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((messages, options, _) =>
            {
                innerConversationIds.Add(options?.ConversationId);
                innerMessageCounts.Add(messages.Count());
            })
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service."))
            {
                ConversationId = "svc"
            });

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        using var chatClient = innerAgent.AsIChatClient();

        var outerAgent = chatClient.AsAIAgent();
        var outerSession = await outerAgent.CreateSessionAsync();

        // Act
        await outerAgent.RunAsync("Hi", outerSession);
        await outerAgent.RunAsync("Again", outerSession);

        // Assert
        Assert.Equal(2, innerConversationIds.Count);
        Assert.All(innerConversationIds, id => Assert.Null(id));

        // No reported id means the outer session stays in local-history mode: it keeps the transcript itself and
        // resends it, which is the only correct behavior over a client that continues nothing.
        Assert.Null(outerSession.GetService<ChatClientAgentSession>()!.ConversationId);
        Assert.True(
            innerMessageCounts[1] > innerMessageCounts[0],
            $"Expected turn 2 to resend the accumulated history, but it sent {innerMessageCounts[1]} messages against {innerMessageCounts[0]} on turn 1.");
    }

    [Fact]
    public async Task AsAIAgent_OverStatelessClientWithPerServiceCallPersistence_RunsTwoTurnsWithoutRejectingTheSentinelAsync()
    {
        // Arrange
        // The same round trip over the sentinel path, which is where an un-cleared id bites hardest: the sentinel is
        // stamped on every response, so an outer session would echo it back on turn 2 and be refused.
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service.")));

        var innerAgent = new ChatClientAgent(
            mockChatClient.Object,
            new ChatClientAgentOptions { RequirePerServiceCallChatHistoryPersistence = true });

        using var chatClient = innerAgent.AsIChatClient();

        var outerAgent = chatClient.AsAIAgent();
        var outerSession = await outerAgent.CreateSessionAsync();

        // Act
        await outerAgent.RunAsync("Hi", outerSession);
        await outerAgent.RunAsync("Again", outerSession);

        // Assert
        Assert.Null(outerSession.GetService<ChatClientAgentSession>()!.ConversationId);
    }

    [Fact]
    public async Task AsAIAgent_OverBoundClient_ContinuesTheInnerSessionAcrossTurnsAsync()
    {
        // Arrange
        // The bound half of the round trip. Here the adapter does report an id, so the outer session switches to
        // service-managed mode on it and stops keeping a transcript of its own: the inner bound session supplies the
        // history instead, which is the division of labour a reported conversation id is meant to signal.
        List<int> innerMessageCounts = [];

        var mockChatClient = new Mock<IChatClient>();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((messages, _, _) => innerMessageCounts.Add(messages.Count()))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Response from the service.")));

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var innerSession = await innerAgent.CreateSessionAsync();

        using var chatClient = innerAgent.AsIChatClient(innerSession, "adapter-conversation");

        var outerAgent = chatClient.AsAIAgent();
        var outerSession = await outerAgent.CreateSessionAsync();

        // Act
        await outerAgent.RunAsync("Hi", outerSession);
        await outerAgent.RunAsync("Again", outerSession);

        // Assert
        Assert.Equal("adapter-conversation", outerSession.GetService<ChatClientAgentSession>()!.ConversationId);

        // Turn 1 sent one user message. Turn 2 reached the service with three — the two the inner bound session had
        // accumulated plus one new — which is only possible if the outer agent sent a single new message rather than
        // resending its own transcript on top of the session's.
        Assert.Equal(2, innerMessageCounts.Count);
        Assert.Equal(1, innerMessageCounts[0]);
        Assert.Equal(3, innerMessageCounts[1]);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithSessionKnowingServiceConversationId_ReportsAdapterIdOnEveryUpdateAsync()
    {
        // Arrange
        // The session holds a real service id and the stream carries a mixture of ids. None of that changes what is
        // reported: in bound mode the client's own id goes out on every update.
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
        using var chatClient = agent.AsIChatClient(session, "adapter-conversation", allowNonChatClientAgents: true);

        // Act
        List<ChatResponseUpdate> receivedUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hi")]))
        {
            receivedUpdates.Add(update);
        }

        // Assert
        Assert.Equal(3, receivedUpdates.Count);

        // Every update is a copy, so the inner client's objects keep whatever ids they arrived with.
        for (var i = 0; i < receivedUpdates.Count; i++)
        {
            Assert.NotSame(rawUpdates[i], receivedUpdates[i]);
        }

        Assert.Equal("known-service-conversation", rawUpdates[0].ConversationId);
        Assert.Null(rawUpdates[1].ConversationId);
        Assert.Equal("some-other-conversation", rawUpdates[2].ConversationId);

        Assert.All(receivedUpdates, update => Assert.Equal("adapter-conversation", update.ConversationId));

        // Re-stamping must not cost anything else: the copies still carry the content they arrived with.
        var aggregated = receivedUpdates.ToChatResponse();
        Assert.Equal("adapter-conversation", aggregated.ConversationId);
        Assert.Equal("onetwothree", aggregated.Text);
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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);
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
        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);

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
    public async Task GetStreamingResponseAsync_WhenServiceConversationIdChangesMidRun_StillReportsTheAdapterIdAsync()
    {
        // Arrange
        // The hard case for any session-derived scheme: the session holds "S1", the stream carries "S2", and the
        // session only catches up as the run ends. A constant id sidesteps all of it — nothing the service does to
        // its own ids can change what this client reports, so what it reports is always what it accepts.
        var session = new ChatClientAgentSession("S1");
        AgentRunOptions? capturedOptions = null;

        async IAsyncEnumerable<AgentResponseUpdate> StreamAsync()
        {
            yield return new(ChatRole.Assistant, "one");
            await Task.Yield();

            yield return new(ChatRole.Assistant, "two")
            {
                RawRepresentation = new ChatResponseUpdate(ChatRole.Assistant, "two") { ConversationId = "S2" }
            };

            // End of run: the session adopts the new id, superseding what was already streamed.
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

        using var chatClient = agent.AsIChatClient(session, "adapter-conversation", allowNonChatClientAgents: true);

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
            // Enumerate to completion; the absence of an InvalidOperationException is part of the assertion.
        }

        // Assert
        Assert.Equal(2, receivedUpdates.Count);
        Assert.All(receivedUpdates, update => Assert.Equal("adapter-conversation", update.ConversationId));
        Assert.Equal("adapter-conversation", reportedConversationId);
        Assert.Null(Assert.IsType<ChatClientAgentRunOptions>(capturedOptions).ChatOptions!.ConversationId);
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

        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);

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

        using var chatClient = agent.AsIChatClient(allowNonChatClientAgents: true);

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
        // The reported id comes from the client, not from the session, so it does not depend on the session type.
        // A session the framework knows nothing about is bound just as well as a ChatClientAgentSession.
        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, cancellationToken) =>
                Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")))
        };

        using var chatClient = agent.AsIChatClient(new UnrecognizedAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);

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
        using var chatClient = agent.AsIChatClient(new ChatClientAgentSession(), "adapter-conversation", allowNonChatClientAgents: true);

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
        using var chatClient = agent.AsIChatClient(session, "secret-adapter-conversation", allowNonChatClientAgents: true);

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
        // the client stamps every update rather than just the first: a single un-stamped update at the tail would
        // otherwise win the aggregate and hand the caller an id it cannot use.
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
    /// An <see cref="AgentSession"/> that is not a <see cref="ChatClientAgentSession"/>, used to show that the
    /// reported conversation id comes from the client's own configuration and not from the session's type or state.
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
