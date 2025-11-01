// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Provides an <see cref="IChatClient"/> implementation that communicates with an AG-UI compliant server.
/// </summary>
internal sealed class AGUIChatClient : IChatClient
{
    private readonly AGUIHttpService _httpService;
    private readonly JsonSerializerOptions _jsonSerializerOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIChatClient"/> class.
    /// </summary>
    /// <param name="httpClient">The HTTP client to use for communication with the AG-UI server.</param>
    /// <param name="endpoint">The URL for the AG-UI server.</param>
    /// <param name="modelId">Optional model identifier for the AG-UI service.</param>
    /// <param name="jsonSerializerOptions">JSON serializer options for tool call argument serialization. If null, AGUIJsonSerializerContext.Default.Options will be used.</param>
    public AGUIChatClient(
        HttpClient httpClient,
        string endpoint,
        string? modelId = null,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (httpClient is null)
        {
            throw new ArgumentNullException(nameof(httpClient));
        }

        if (string.IsNullOrEmpty(endpoint))
        {
            throw new ArgumentException("Endpoint cannot be null or empty.", nameof(endpoint));
        }

        this._httpService = new AGUIHttpService(httpClient, endpoint);
        this._jsonSerializerOptions = jsonSerializerOptions ?? AGUIJsonSerializerContext.Default.Options;
        this.Metadata = new ChatClientMetadata("AGUI", new Uri(endpoint, UriKind.RelativeOrAbsolute), modelId);
    }

    /// <inheritdoc/>
    public ChatClientMetadata Metadata { get; }

    /// <inheritdoc/>
    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var updates = new List<ChatResponseUpdate>();

        await foreach (var update in this.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
        }

        return updates.ToChatResponse();
    }

    /// <inheritdoc/>
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (messages is null)
        {
            throw new ArgumentNullException(nameof(messages));
        }

        var messagesList = messages.ToList();

        // Extract thread ID from options if available
        string threadId = options?.ConversationId ?? Guid.NewGuid().ToString();
        string runId = Guid.NewGuid().ToString();

        // Create the input for the AGUI service
        var input = new RunAgentInput
        {
            ThreadId = threadId,
            RunId = runId,
            Messages = messagesList.AsAGUIMessages(this._jsonSerializerOptions),
        };

        // Add tools if provided
        if (options?.Tools is { Count: > 0 })
        {
            input.Tools = options.Tools.AsAGUITools();
        }

        // Stream the response from the AGUI service
        await foreach (var update in this._httpService.PostRunAsync(input, cancellationToken)
            .AsChatResponseUpdatesAsync(this._jsonSerializerOptions, cancellationToken)
            .ConfigureAwait(false))
        {
            yield return update;
        }
    }

    /// <inheritdoc/>
    public TService? GetService<TService>(object? key = null) where TService : class
    {
        return this as TService;
    }

    /// <inheritdoc/>
    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        if (serviceType == typeof(ChatClientMetadata))
        {
            return this.Metadata;
        }

        if (serviceType?.IsInstanceOfType(this) == true)
        {
            return this;
        }

        return null;
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        // No resources to dispose
    }
}
