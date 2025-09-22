// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Hosting;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace AgentWebChat.Web;

internal sealed class HttpActorClient(HttpClient httpClient) : IActorClient
{
    private const string BaseUri = "/actors/v1";

    public async ValueTask<ActorResponseHandle> GetResponseAsync(ActorId actorId, string messageId, CancellationToken cancellationToken)
    {
        var uri = new Uri($"{BaseUri}/{actorId.Type}/{actorId.Key}/{messageId}", UriKind.Relative);
        var response = await httpClient.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        return new HttpActorResponseHandle(httpClient, actorId, messageId, initialResponseMessage: response);
    }

    public async ValueTask<ActorResponseHandle> SendRequestAsync(ActorRequest request, CancellationToken cancellationToken)
    {
        var actorId = request.ActorId;
        var messageId = request.MessageId;
        var uri = new Uri($"{BaseUri}/{actorId.Type}/{actorId.Key}/{messageId}?streaming=true", UriKind.Relative);
        var jsonContent = JsonContent.Create(request, AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ActorRequest)));
        var message = new HttpRequestMessage(HttpMethod.Post, uri) { Content = jsonContent };
        var response = await httpClient.SendAsync(message, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        return new HttpActorResponseHandle(httpClient, actorId, messageId, response);
    }

    private sealed class HttpActorResponseHandle(
        HttpClient httpClient,
        ActorId actorId,
        string messageId,
        HttpResponseMessage? initialResponseMessage) : ActorResponseHandle
    {
        private HttpResponseMessage? _responseMessage = initialResponseMessage;
        private ActorResponse? _lastResponse;

        public override async ValueTask CancelAsync(CancellationToken cancellationToken)
        {
            this._responseMessage?.Dispose();
            this._responseMessage = null;

            var uri = new Uri($"{BaseUri}/{actorId.Type}/{actorId.Key}/{messageId}:cancel", UriKind.Relative);
            await httpClient.PostAsync(uri, null, cancellationToken).ConfigureAwait(false);
        }

        public override async ValueTask<ActorResponse> GetResponseAsync(CancellationToken cancellationToken)
        {
            try
            {
                // If the response is already completed, don't bother requesting the response again;
                if (this._lastResponse is { } response && response.Status.IsTerminated())
                {
                    return response;
                }

                if (IsStreamingResponse(this._responseMessage))
                {
                    try
                    {
                        var updates = new List<AgentRunResponseUpdate>();
                        await foreach (var update in EnumerateAsync(this._responseMessage, cancellationToken).ConfigureAwait(false))
                        {
                            if (!update.Status.IsTerminated())
                            {
                                continue;
                            }

                            response = new ActorResponse { ActorId = actorId, MessageId = messageId, Status = update.Status, Data = update.Data };
                            this._lastResponse = response;
                            return response;
                        }
                    }
                    finally
                    {
                        this._responseMessage?.Dispose();
                        this._responseMessage = null;
                    }
                }

                var uri = new Uri($"{BaseUri}/{actorId.Type}/{actorId.Key}/{messageId}?blocking=true", UriKind.Relative);
                using var responseMessage = this._responseMessage ?? await httpClient.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
                response = await this.ReadResponseAsync(responseMessage, cancellationToken).ConfigureAwait(false);
                this._lastResponse = response;
                return response;
            }
            finally
            {
                this._responseMessage = null;
            }
        }

        public override bool TryGetResponse([NotNullWhen(true)] out ActorResponse? response)
        {
            response = this._lastResponse;
            return response is not null;
        }

        public override async IAsyncEnumerable<ActorRequestUpdate> WatchUpdatesAsync([EnumeratorCancellation] CancellationToken cancellationToken)
        {
            // If the response is already completed, don't bother streaming anything.
            if (this._lastResponse is { } response && response.Status.IsTerminated())
            {
                yield return new ActorRequestUpdate(response.Status, response.Data);
                yield break;
            }

            try
            {
                var uri = new Uri($"{BaseUri}/{actorId.Type}/{actorId.Key}/{messageId}?streaming=true", UriKind.Relative);
                using var responseMessage = this._responseMessage ?? await httpClient.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
                if (IsJsonResponse(responseMessage))
                {
                    // If the response is JSON, read it as a single response and yield it.
                    response = await this.ReadResponseAsync(responseMessage, cancellationToken).ConfigureAwait(false);

                    yield return new ActorRequestUpdate(response.Status, response.Data);
                    yield break;
                }

                await foreach (var update in EnumerateAsync(responseMessage, cancellationToken).ConfigureAwait(false))
                {
                    yield return update;
                }
            }
            finally
            {
                this._responseMessage = null;
            }
        }

        private static async IAsyncEnumerable<ActorRequestUpdate> EnumerateAsync(HttpResponseMessage responseMessage, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            var responseStream = await responseMessage.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
            var sseParser = SseParser.Create(responseStream, (eventType, data) =>
            {
                if (eventType != "message")
                {
                    // Only process default message events
                    return null;
                }

                var reader = new Utf8JsonReader(data);
                return JsonSerializer.Deserialize(ref reader, AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ActorRequestUpdate))) as ActorRequestUpdate;
            });

            await foreach (var item in sseParser.EnumerateAsync(cancellationToken).ConfigureAwait(false))
            {
                if (item.Data is not null)
                {
                    yield return item.Data;
                }
            }
        }

        private async Task<ActorResponse> ReadResponseAsync(HttpResponseMessage responseMessage, CancellationToken cancellationToken) =>
            await responseMessage.Content.ReadFromJsonAsync<ActorResponse>(AgentRuntimeJsonUtilities.DefaultOptions, cancellationToken).ConfigureAwait(false) ??
            throw new InvalidOperationException($"No response found for actor '{actorId}' with message ID '{messageId}'.");

        private static bool IsJsonResponse([NotNullWhen(true)] HttpResponseMessage? response) => response?.Content.Headers.ContentType?.MediaType == "application/json";

        private static bool IsStreamingResponse([NotNullWhen(true)] HttpResponseMessage? response) => response?.Content.Headers.ContentType?.MediaType == "text/event-stream";

        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            this._responseMessage?.Dispose();
            this._responseMessage = null;
        }
    }
}
