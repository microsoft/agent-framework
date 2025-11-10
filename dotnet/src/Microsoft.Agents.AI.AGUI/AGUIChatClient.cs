// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Provides an <see cref="IChatClient"/> implementation that communicates with an AG-UI compliant server.
/// </summary>
public sealed class AGUIChatClient : DelegatingChatClient
{
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
            CombineJsonSerializerOptions(jsonSerializerOptions),
            loggerFactory,
            serviceProvider))
    {
    }

    private static JsonSerializerOptions CombineJsonSerializerOptions(JsonSerializerOptions? jsonSerializerOptions)
    {
        if (jsonSerializerOptions == null)
        {
            return AGUIJsonSerializerContext.Default.Options;
        }

        // Create a new JsonSerializerOptions based on the provided one
        var combinedOptions = new JsonSerializerOptions(jsonSerializerOptions);

        // Add the AGUI context to the type info resolver chain if not already present
        if (!combinedOptions.TypeInfoResolverChain.Any(r => r == AGUIJsonSerializerContext.Default))
        {
            combinedOptions.TypeInfoResolverChain.Insert(0, AGUIJsonSerializerContext.Default);
        }

        return combinedOptions;
    }

    private static FunctionInvokingChatClient CreateInnerClient(
        HttpClient httpClient,
        string endpoint,
        JsonSerializerOptions jsonSerializerOptions,
        ILoggerFactory? loggerFactory,
        IServiceProvider? serviceProvider)
    {
        Throw.IfNull(httpClient);
        Throw.IfNull(endpoint);
        var handler = new AGUIChatClientHandler(httpClient, endpoint, jsonSerializerOptions, serviceProvider);
        return new FunctionInvokingChatClient(handler, loggerFactory, serviceProvider);
    }

    /// <inheritdoc />
    public override Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        this.GetStreamingResponseAsync(messages, options, cancellationToken)
            .ToChatResponseAsync(cancellationToken);

    /// <inheritdoc />
    public async override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ChatResponseUpdate? firstUpdate = null;
        string? conversationId = null;
        // AG-UI requires the full message history on every turn, so we clear the conversation id here
        // and restore it for the caller.
        var innerOptions = options;
        if (options?.ConversationId != null)
        {
            conversationId = options.ConversationId;

            // Clone the options and set the conversation ID to null so the FunctionInvokingChatClient doesn't see it.
            innerOptions = options.Clone();
            innerOptions.AdditionalProperties ??= [];
            innerOptions.AdditionalProperties["agui_thread_id"] = options.ConversationId;
            innerOptions.ConversationId = null;
        }

        await foreach (var update in base.GetStreamingResponseAsync(messages, innerOptions, cancellationToken).ConfigureAwait(false))
        {
            if (conversationId == null && firstUpdate == null)
            {
                firstUpdate = update;
                if (firstUpdate.AdditionalProperties?.TryGetValue("agui_thread_id", out string? threadId) is true)
                {
                    // Capture the thread id from the first update to use as conversation id if none was provided
                    conversationId = threadId;
                }
            }

            // Cleanup any temporary approach we used by the handler to avoid issues with FunctionInvokingChatClient
            for (var i = 0; i < update.Contents.Count; i++)
            {
                var content = update.Contents[i];
                if (content is FunctionCallContent functionCallContent)
                {
                    functionCallContent.AdditionalProperties?.Remove("agui_thread_id");
                }
                if (content is ServerFunctionCallContent serverFunctionCallContent)
                {
                    update.Contents[i] = serverFunctionCallContent.FunctionCallContent;
                }
            }

            var finalUpdate = CopyResponseUpdate(update);

            finalUpdate.ConversationId = conversationId;
            yield return finalUpdate;
        }
    }

    private static ChatResponseUpdate CopyResponseUpdate(ChatResponseUpdate source)
    {
        return new ChatResponseUpdate
        {
            AuthorName = source.AuthorName,
            Role = source.Role,
            Contents = source.Contents,
            RawRepresentation = source.RawRepresentation,
            AdditionalProperties = source.AdditionalProperties,
            ResponseId = source.ResponseId,
            MessageId = source.MessageId,
            CreatedAt = source.CreatedAt,
        };
    }

    private sealed class AGUIChatClientHandler : IChatClient
    {
        private static readonly MediaTypeHeaderValue s_json = new("application/json");

        private readonly AGUIHttpService _httpService;
        private readonly JsonSerializerOptions _jsonSerializerOptions;
        private readonly ILogger _logger;

        public AGUIChatClientHandler(
            HttpClient httpClient,
            string endpoint,
            JsonSerializerOptions? jsonSerializerOptions,
            IServiceProvider? serviceProvider)
        {
            this._httpService = new AGUIHttpService(httpClient, endpoint);
            this._jsonSerializerOptions = jsonSerializerOptions ?? AGUIJsonSerializerContext.Default.Options;
            this._logger = serviceProvider?.GetService(typeof(ILogger<AGUIChatClient>)) as ILogger ?? NullLogger.Instance;

            // Use BaseAddress if endpoint is empty, otherwise parse as relative or absolute
            Uri metadataUri = string.IsNullOrEmpty(endpoint) && httpClient.BaseAddress is not null
                ? httpClient.BaseAddress
                : new Uri(endpoint, UriKind.RelativeOrAbsolute);
            this.Metadata = new ChatClientMetadata("ag-ui", metadataUri, null);
        }

        public ChatClientMetadata Metadata { get; }

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            return this.GetStreamingResponseAsync(messages, options, cancellationToken)
                .ToChatResponseAsync(cancellationToken);
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

            var runId = $"run_{Guid.NewGuid():N}";
            var messagesList = messages.ToList(); // Avoid triggering the enumerator multiple times.
            var threadId = ExtractTemporaryThreadId(messagesList) ??
                ExtractThreadIdFromOptions(options) ?? $"thread_{Guid.NewGuid():N}";

            // Extract state from the last message if it contains DataContent with application/json
            JsonElement state = this.ExtractAndRemoveStateFromMessages(messagesList);

            // Create the input for the AGUI service
            var input = new RunAgentInput
            {
                // AG-UI requires a thread ID to work, but for FunctionInvokingChatClient that
                // implies the underlying client is managing the history.
                ThreadId = threadId,
                RunId = runId,
                Messages = messagesList.AsAGUIMessages(this._jsonSerializerOptions),
                State = state,
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

            ChatResponseUpdate? firstUpdate = null;
            await foreach (var update in this._httpService.PostRunAsync(input, cancellationToken)
                .AsChatResponseUpdatesAsync(this._jsonSerializerOptions, cancellationToken).ConfigureAwait(false))
            {
                if (firstUpdate == null)
                {
                    firstUpdate = update;
                    if (!string.IsNullOrEmpty(firstUpdate.ConversationId) && !string.Equals(firstUpdate.ConversationId, threadId, StringComparison.Ordinal))
                    {
                        threadId = firstUpdate.ConversationId;
                    }
                    firstUpdate.AdditionalProperties ??= [];
                    firstUpdate.AdditionalProperties["agui_thread_id"] = threadId;
                }

                if (update.Contents is { Count: 1 } && update.Contents[0] is FunctionCallContent fcc)
                {
                    if (clientToolSet.Contains(fcc.Name))
                    {
                        // Prepare to let the wrapping FunctionInvokingChatClient handle this function call.
                        // We want to retain the original thread id that either the server sent us or that we set
                        // in this turn on the next turn, but we can't make it visible to FunctionInvokeingChatClient
                        // because it would then not send the full history on the next turn as required by AG-UI.
                        // We store it on additional properties of the function call content, which will be passed down
                        // in the next turn.
                        fcc.AdditionalProperties ??= [];
                        fcc.AdditionalProperties["agui_thread_id"] = threadId;
                    }
                    else
                    {
                        // Hide the server result call from the FunctionInvokingChatClient.
                        // The wrapping client will unwrap it and present it as a normal function result.
                        update.Contents[0] = new ServerFunctionCallContent(fcc);
                    }
                }

                // Remove the conversation id before yielding so that the wrapping FunctionInvokingChatClient
                // sends the whole message history on every turn as per AG-UI requirements.
                update.ConversationId = null;
                yield return update;
            }
        }

        // Extract the thread id from the options additional properties
        private static string? ExtractThreadIdFromOptions(ChatOptions? options)
        {
            if (options?.AdditionalProperties is null ||
              !options.AdditionalProperties.TryGetValue("agui_thread_id", out string? threadId) ||
              string.IsNullOrEmpty(threadId))
            {
                return null;
            }
            return threadId;
        }

        // Extract the thread id from the second last message's function call content additional properties
        private static string? ExtractTemporaryThreadId(List<ChatMessage> messagesList)
        {
            if (messagesList.Count < 2)
            {
                return null;
            }
            var functionCall = messagesList[messagesList.Count - 2];
            if (functionCall.Contents.Count < 1 || functionCall.Contents[0] is not FunctionCallContent content)
            {
                return null;
            }

            if (content.AdditionalProperties is null ||
              !content.AdditionalProperties.TryGetValue("agui_thread_id", out string? threadId) ||
              string.IsNullOrEmpty(threadId))
            {
                return null;
            }

            return threadId;
        }

        // Extract state from the last message's DataContent with application/json media type
        // and remove that message from the list
        private JsonElement ExtractAndRemoveStateFromMessages(List<ChatMessage> messagesList)
        {
            if (messagesList.Count == 0)
            {
                return default;
            }

            // Check the last message for state DataContent
            ChatMessage lastMessage = messagesList[messagesList.Count - 1];
            for (int i = 0; i < lastMessage.Contents.Count; i++)
            {
                if (lastMessage.Contents[i] is DataContent dataContent &&
                    MediaTypeHeaderValue.TryParse(dataContent.MediaType, out var mediaType) &&
                    mediaType.Equals(s_json))
                {
                    // Deserialize the state JSON directly from UTF-8 bytes
                    try
                    {
                        JsonElement stateElement = (JsonElement)JsonSerializer.Deserialize(
                            dataContent.Data.Span,
                            this._jsonSerializerOptions.GetTypeInfo(typeof(JsonElement)))!;

                        // Remove the DataContent from the message contents
                        lastMessage.Contents.RemoveAt(i);

                        // If no contents remain, remove the entire message
                        if (lastMessage.Contents.Count == 0)
                        {
                            messagesList.RemoveAt(messagesList.Count - 1);
                        }

                        return stateElement;
                    }
                    catch (JsonException ex)
                    {
                        throw new InvalidOperationException($"Failed to deserialize state JSON from DataContent: {ex.Message}", ex);
                    }
                }
            }

            return default;
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

    private sealed class ServerFunctionCallContent(FunctionCallContent functionCall) : AIContent
    {
        public FunctionCallContent FunctionCallContent { get; } = functionCall;
    }
}
