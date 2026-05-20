// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;

#pragma warning disable OPENAI001, MEAI001, MAAI001, SCME0001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Tests for the <c>x-ms-served-model</c> response header pipeline:
/// <see cref="ServedModelScope"/> AsyncLocal carrier,
/// <see cref="ServedModelPolicy"/> pipeline policy,
/// and <see cref="ServedModelChatClient"/> delegating client.
/// </summary>
public sealed class ServedModelTests
{
    // ===========================================================================================
    // ServedModelScope tests
    // ===========================================================================================

    [Fact]
    public void Scope_DefaultIsNull()
    {
        Assert.Null(ServedModelScope.Current);
    }

    [Fact]
    public void Scope_SetAndGet_ReturnsBox()
    {
        var previous = ServedModelScope.Current;
        try
        {
            var box = new StrongBox<string?>("gpt-5-nano-2025-08-07");
            ServedModelScope.Current = box;
            Assert.Same(box, ServedModelScope.Current);
            Assert.Equal("gpt-5-nano-2025-08-07", ServedModelScope.Current!.Value);
        }
        finally
        {
            ServedModelScope.Current = previous;
        }
    }

    // ===========================================================================================
    // ServedModelPolicy tests (via real SCM pipeline + mock HTTP handler)
    // ===========================================================================================

    [Fact]
    public void Policy_IsSingleton()
    {
        Assert.Same(ServedModelPolicy.Instance, ServedModelPolicy.Instance);
    }

    [Fact]
    public async Task Policy_HeaderPresent_SetsScopeAsync()
    {
        // Arrange
        using var handler = new ServedModelHandler(MinimalResponseJson(), servedModel: "gpt-5-nano-2025-08-07");
        IChatClient chatClient = CreateChatClientWithPolicy(handler);

        // Act: drive a request through the pipeline. The policy fires during the HTTP roundtrip.
        var response = await chatClient.GetResponseAsync("hi");

        // Assert: the scope was populated during the call, but we need a way to observe it.
        // The end-to-end test validates this via ServedModelChatClient. Here we confirm the
        // scope is set by wrapping with ServedModelChatClient and checking the result.
        Assert.Equal("gpt-5-nano-2025-08-07", response.ModelId);
    }

    [Fact]
    public async Task Policy_HeaderAbsent_ScopeRemainsNull_ModelIdUnchangedAsync()
    {
        // Arrange
        using var handler = new ServedModelHandler(MinimalResponseJson(), servedModel: null);
        IChatClient chatClient = CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert: ModelId is the deployment alias from the JSON body ("fake").
        Assert.Equal("fake", response.ModelId);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public async Task Policy_EmptyOrWhitespaceHeader_ModelIdUnchangedAsync(string headerValue)
    {
        // Arrange
        using var handler = new ServedModelHandler(MinimalResponseJson(), servedModel: headerValue);
        IChatClient chatClient = CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert: empty/whitespace header is rejected by the policy, ModelId stays as "fake".
        Assert.Equal("fake", response.ModelId);
    }

    [Fact]
    public async Task Policy_HeaderWithWhitespace_TrimsValueAsync()
    {
        // Arrange
        using var handler = new ServedModelHandler(MinimalResponseJson(), servedModel: "  gpt-5-nano-2025-08-07  ");
        IChatClient chatClient = CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert: the whitespace is trimmed.
        Assert.Equal("gpt-5-nano-2025-08-07", response.ModelId);
    }

    // ===========================================================================================
    // ServedModelChatClient tests (non-streaming)
    // ===========================================================================================

    [Fact]
    public async Task GetResponseAsync_PolicySetsBox_OverwritesModelIdAsync()
    {
        // Arrange: fake inner client that simulates the policy writing into the box during the call.
        var inner = new FakeChatClientWithPolicySimulation("deployment-alias", "gpt-5-nano-2025-08-07");
        var client = new ServedModelChatClient(inner);

        // Act
        var response = await client.GetResponseAsync([]);

        // Assert
        Assert.Equal("gpt-5-nano-2025-08-07", response.ModelId);
    }

    [Fact]
    public async Task GetResponseAsync_PolicyDoesNotSetBox_PreservesOriginalModelIdAsync()
    {
        // Arrange: fake inner client that does NOT write to the box (simulates absent header).
        var inner = new FakeChatClient("deployment-alias");
        var client = new ServedModelChatClient(inner);

        // Act
        var response = await client.GetResponseAsync([]);

        // Assert
        Assert.Equal("deployment-alias", response.ModelId);
    }

    // ===========================================================================================
    // ServedModelChatClient tests (streaming)
    // ===========================================================================================

    [Fact]
    public async Task GetStreamingResponseAsync_PolicySetsBox_OverwritesModelIdOnAllUpdatesAsync()
    {
        // Arrange: fake inner client that simulates the policy writing into the box.
        var inner = new FakeStreamingChatClientWithPolicySimulation("deployment-alias", "gpt-5-nano-2025-08-07", updateCount: 3);
        var client = new ServedModelChatClient(inner);

        // Act
        var updates = new List<ChatResponseUpdate>();
        await foreach (var update in client.GetStreamingResponseAsync([]))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(3, updates.Count);
        Assert.All(updates, u => Assert.Equal("gpt-5-nano-2025-08-07", u.ModelId));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_PolicyDoesNotSetBox_PreservesOriginalModelIdAsync()
    {
        // Arrange: fake inner client that does NOT write to the box.
        var inner = new FakeStreamingChatClient("deployment-alias", updateCount: 2);
        var client = new ServedModelChatClient(inner);

        // Act
        var updates = new List<ChatResponseUpdate>();
        await foreach (var update in client.GetStreamingResponseAsync([]))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.All(updates, u => Assert.Equal("deployment-alias", u.ModelId));
    }

    // ===========================================================================================
    // End-to-end tests (policy + client together via real OpenAI SCM pipeline)
    // ===========================================================================================

    [Fact]
    public async Task EndToEnd_PolicyAndClient_ModelIdReflectsServedModelAsync()
    {
        // Arrange
        using var handler = new ServedModelHandler(MinimalResponseJson(), servedModel: "gpt-5-nano-2025-08-07");
        IChatClient chatClient = CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert
        Assert.Equal("gpt-5-nano-2025-08-07", response.ModelId);
    }

    [Fact]
    public async Task EndToEnd_PolicyAndClient_NoHeader_ModelIdUnchangedAsync()
    {
        // Arrange
        using var handler = new ServedModelHandler(MinimalResponseJson(), servedModel: null);
        IChatClient chatClient = CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert
        Assert.Equal("fake", response.ModelId);
    }

    // ===========================================================================================
    // Helpers
    // ===========================================================================================

    private static string MinimalResponseJson() => """
        {
          "id":"resp_1","object":"response","created_at":1700000000,"status":"completed",
          "model":"fake","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}
        }
        """;

    /// <summary>
    /// Creates a chat client backed by a real OpenAI ResponsesClient with the
    /// <see cref="ServedModelPolicy"/> registered and wrapped by <see cref="ServedModelChatClient"/>.
    /// </summary>
    private static IChatClient CreateChatClientWithPolicy(HttpMessageHandler handler)
    {
#pragma warning disable CA5399
        var http = new HttpClient(handler);
#pragma warning restore CA5399
        var openAIOptions = new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) };
        var openAIClient = new OpenAIClient(new ApiKeyCredential("fake"), openAIOptions);
        var responsesClient = openAIClient.GetResponsesClient();

        IChatClient chatClient = responsesClient.AsIChatClient();
        chatClient = FoundryAgent.WireServedModel(chatClient);

        return chatClient;
    }

    /// <summary>
    /// An <see cref="HttpClientHandler"/> that returns a fixed response body and optionally
    /// includes the <c>x-ms-served-model</c> response header.
    /// </summary>
    private sealed class ServedModelHandler : HttpClientHandler
    {
        private readonly string _body;
        private readonly string? _servedModel;

        public ServedModelHandler(string body, string? servedModel)
        {
            this._body = body;
            this._servedModel = servedModel;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var resp = new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(this._body, Encoding.UTF8, "application/json"),
                RequestMessage = request,
            };

            if (this._servedModel is not null)
            {
                resp.Headers.Add("x-ms-served-model", this._servedModel);
            }

            return Task.FromResult(resp);
        }
    }

    /// <summary>
    /// A minimal <see cref="IChatClient"/> that returns a <see cref="ChatResponse"/> with the given model ID.
    /// </summary>
    private sealed class FakeChatClient : IChatClient
    {
        private readonly string _modelId;

        public FakeChatClient(string modelId)
        {
            this._modelId = modelId;
        }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "hi")]) { ModelId = this._modelId });

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose() { }
    }

    /// <summary>
    /// A minimal <see cref="IChatClient"/> that yields <see cref="ChatResponseUpdate"/>s with a given model ID.
    /// </summary>
    private sealed class FakeStreamingChatClient : IChatClient
    {
        private readonly string _modelId;
        private readonly int _updateCount;

        public FakeStreamingChatClient(string modelId, int updateCount)
        {
            this._modelId = modelId;
            this._updateCount = updateCount;
        }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            for (int i = 0; i < this._updateCount; i++)
            {
                await Task.Yield();
                yield return new ChatResponseUpdate { ModelId = this._modelId };
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose() { }
    }

    /// <summary>
    /// A fake <see cref="IChatClient"/> that simulates the <see cref="ServedModelPolicy"/> by writing
    /// into the <see cref="ServedModelScope"/> box during <see cref="GetResponseAsync"/>.
    /// </summary>
    private sealed class FakeChatClientWithPolicySimulation : IChatClient
    {
        private readonly string _modelId;
        private readonly string _servedModel;

        public FakeChatClientWithPolicySimulation(string modelId, string servedModel)
        {
            this._modelId = modelId;
            this._servedModel = servedModel;
        }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            // Simulate what ServedModelPolicy does: write into the box.
            if (ServedModelScope.Current is { } box)
            {
                box.Value = this._servedModel;
            }

            return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "hi")]) { ModelId = this._modelId });
        }

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose() { }
    }

    /// <summary>
    /// A fake streaming <see cref="IChatClient"/> that simulates the <see cref="ServedModelPolicy"/>
    /// by writing into the <see cref="ServedModelScope"/> box before yielding updates.
    /// </summary>
    private sealed class FakeStreamingChatClientWithPolicySimulation : IChatClient
    {
        private readonly string _modelId;
        private readonly string _servedModel;
        private readonly int _updateCount;

        public FakeStreamingChatClientWithPolicySimulation(string modelId, string servedModel, int updateCount)
        {
            this._modelId = modelId;
            this._servedModel = servedModel;
            this._updateCount = updateCount;
        }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            // Simulate what ServedModelPolicy does on the initial HTTP response.
            if (ServedModelScope.Current is { } box)
            {
                box.Value = this._servedModel;
            }

            for (int i = 0; i < this._updateCount; i++)
            {
                await Task.Yield();
                yield return new ChatResponseUpdate { ModelId = this._modelId };
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose() { }
    }
}
