// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Provides an <see cref="IChatClient"/> implementation that communicates with an AG-UI compliant server.
/// </summary>
public sealed class AGUIChatClient : DelegatingChatClient
{
    private readonly List<ChatResponseUpdate> _executedServerFunctionStream = [];

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIChatClient"/> class.
    /// </summary>
    /// <param name="httpClient">The HTTP client to use for communication with the AG-UI server.</param>
    /// <param name="endpoint">The URL for the AG-UI server.</param>
    /// <param name="loggerFactory">The <see cref="ILoggerFactory"/> to use for logging.</param>
    /// <param name="jsonSerializerOptions">JSON serializer options for tool call argument serialization. If null, AGUIJsonSerializerContext.Default.Options will be used.</param>
    /// <param name="serviceProvider">Optional service provider for resolving dependencies like ILogger.</param>
    public AGUIChatClient(
        HttpClient httpClient,
        string endpoint,
        ILoggerFactory? loggerFactory = null,
        JsonSerializerOptions? jsonSerializerOptions = null,
        IServiceProvider? serviceProvider = null) : base(CreateInnerClient(
            httpClient,
            endpoint,
            out var executedServerFunctionStream,
            jsonSerializerOptions ?? AGUIJsonSerializerContext.Default.Options,
            loggerFactory,
            serviceProvider))
    {
        this._executedServerFunctionStream = executedServerFunctionStream;
    }

    private static IChatClient CreateInnerClient(
        HttpClient httpClient,
        string endpoint,
        out List<ChatResponseUpdate> executedServerFunctionStream,
        JsonSerializerOptions jsonSerializerOptions,
        ILoggerFactory? loggerFactory,
        IServiceProvider? serviceProvider)
    {
        executedServerFunctionStream = [];
        var handler = new AGUIChatClientHandler(httpClient, endpoint, executedServerFunctionStream, jsonSerializerOptions, serviceProvider);
        return new FunctionInvokingChatClient(handler, loggerFactory, serviceProvider);
    }

    /// <inheritdoc />
    public async override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
        {
            // We bypass the underlying FunctionInvokingChatClient for any server executed function.
            // This is because it will try to invoke it and fail because it can't find the function.
            // There are ways in which we could make it work and return the existing result (with a FunctionInvoker) but we would need to very
            // carefully manage the buffering to preserve the order of updates.
            // This is because FunctionInvokingChatClient will process all updates in a turn and then trigger the function invocation process,
            // meaning that any text update after a server function call would jump out of order on the stream.
            // Instead, we buffer any server function updates internally, and after each update we check if we have something buffered to yield.
            // This way we preserve the order and don't have to manage it inside function invoking client.
            if (this._executedServerFunctionStream.Count > 0)
            {
                foreach (var executedFunctionUpdate in this._executedServerFunctionStream)
                {
                    yield return executedFunctionUpdate;
                }
                this._executedServerFunctionStream.Clear();
            }

            yield return update;
        }

        // In case the functions happened at the end of the stream, yield them now
        foreach (var executedFunctionUpdate in this._executedServerFunctionStream)
        {
            yield return executedFunctionUpdate;
        }
        this._executedServerFunctionStream.Clear();
    }

    private sealed class AGUIChatClientHandler : IChatClient
    {
        private readonly AGUIHttpService _httpService;
        private readonly JsonSerializerOptions _jsonSerializerOptions;

        private readonly List<ChatResponseUpdate> _serverFunctionUpdates = [];
        private readonly ILogger _logger;

        public AGUIChatClientHandler(
            HttpClient httpClient,
            string endpoint,
            List<ChatResponseUpdate> serverFunctionUpdates,
            JsonSerializerOptions? jsonSerializerOptions,
            IServiceProvider? serviceProvider)
        {
            if (httpClient is null)
            {
                throw new ArgumentNullException(nameof(httpClient));
            }

            if (endpoint is null)
            {
                throw new ArgumentNullException(nameof(endpoint));
            }

            this._httpService = new AGUIHttpService(httpClient, endpoint);
            this._jsonSerializerOptions = jsonSerializerOptions ?? AGUIJsonSerializerContext.Default.Options;
            this._serverFunctionUpdates = serverFunctionUpdates;
            this._logger = serviceProvider?.GetService(typeof(ILogger<AGUIChatClient>)) as ILogger ?? NullLogger.Instance;

            // Use BaseAddress if endpoint is empty, otherwise parse as relative or absolute
            Uri metadataUri = string.IsNullOrEmpty(endpoint) && httpClient.BaseAddress is not null
                ? httpClient.BaseAddress
                : new Uri(endpoint, UriKind.RelativeOrAbsolute);
            this.Metadata = new ChatClientMetadata("AGUI", metadataUri, null);
        }

        public ChatClientMetadata Metadata { get; }

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            Debug.Fail("Use GetStreamingResponseAsync instead.");
            throw new NotSupportedException("AGUIChatClientHandler only supports streaming responses. Use GetStreamingResponseAsync instead.");
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (messages is null)
            {
                throw new ArgumentNullException(nameof(messages));
            }

            var runId = $"run_{Guid.NewGuid()}";
            var manufacturedThreadId = $"thread_{Guid.NewGuid()}";
            var threadId = options?.ConversationId ?? manufacturedThreadId;

            // Create the input for the AGUI service
            var input = new RunAgentInput
            {
                // AG-UI requires a thread ID to work, but for FunctionInvokingChatClient that
                // implies the underlying client is managing the history.
                ThreadId = threadId,
                RunId = runId,
                Messages = messages.AsAGUIMessages(this._jsonSerializerOptions),
            };

            // Add tools if provided
            if (options?.Tools is { Count: > 0 })
            {
                input.Tools = options.Tools.AsAGUITools();
                this._logger.LogDebug("[AGUIChatClient] Tool count: {ToolCount}", options.Tools.Count);
            }

            var clientToolSet = new HashSet<string>();
            foreach (var tool in options?.Tools ?? [])
            {
                clientToolSet.Add(tool.Name);
            }

            await foreach (var update in this._httpService.PostRunAsync(input, cancellationToken)
                .AsChatResponseUpdatesAsync(this._jsonSerializerOptions, cancellationToken).ConfigureAwait(false))
            {
                if (string.Equals(update.ConversationId, manufacturedThreadId, StringComparison.Ordinal))
                {
                    // If we manufactured a conversation ID for the sake of being AG-UI compliant, hide it from the function invoking chat client.
                    update.ConversationId = null;
                }
                else if (!string.IsNullOrEmpty(update.ConversationId))
                {
                    threadId = update.ConversationId;
                }

                if (update.Contents is { Count: 1 })
                {
                    if ((update.Contents[0] is FunctionCallContent fcc &&
                        !clientToolSet.Contains(fcc.Name)) || update.Contents[0] is FunctionResultContent)
                    {
                        // Store server executed function updates, we will yield them before we yield the next update
                        // to the agent but we will bypass the FunctionInvokingChatClient processing.
                        this._serverFunctionUpdates.Add(update);
                        continue;
                    }
                }

                yield return update;
            }

            this._logger.LogInformation("[AGUIChatClient] Request completed - ThreadId: {ThreadId}, RunId: {RunId}", "", runId);
        }

        public void Dispose()
        {
            // No resources to dispose
        }

        public object? GetService(Type serviceType, object? serviceKey = null)
        {
            if (serviceType == typeof(ChatClientMetadata))
            {
                return this.Metadata;
            }

            return null;
        }
    }
}
