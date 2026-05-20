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
/// Shared helpers and fake clients used by the served-model test suite
/// (<see cref="ServedModelScopeTests"/>, <see cref="ServedModelPolicyTests"/>,
/// <see cref="ServedModelChatClientTests"/>).
/// </summary>
internal static class ServedModelTestHelpers
{
    public static string MinimalResponseJson() => """
        {
          "id":"resp_1","object":"response","created_at":1700000000,"status":"completed",
          "model":"fake","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}
        }
        """;

    /// <summary>
    /// Creates a chat client backed by a real OpenAI ResponsesClient with the
    /// <see cref="ServedModelPolicy"/> registered and wrapped by <see cref="ServedModelChatClient"/>.
    /// </summary>
    public static IChatClient CreateChatClientWithPolicy(HttpMessageHandler handler)
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
    public sealed class ServedModelHandler : HttpClientHandler
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
    public sealed class FakeChatClient : IChatClient
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
    public sealed class FakeStreamingChatClient : IChatClient
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
    public sealed class FakeChatClientWithPolicySimulation : IChatClient
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
    public sealed class FakeStreamingChatClientWithPolicySimulation : IChatClient
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
