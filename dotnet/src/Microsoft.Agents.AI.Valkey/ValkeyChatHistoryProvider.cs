// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using Valkey.Glide;

namespace Microsoft.Agents.AI.Valkey;

/// <summary>
/// Provides a Valkey-backed implementation of <see cref="ChatHistoryProvider"/> for persistent chat history storage.
/// </summary>
/// <remarks>
/// <para>
/// Uses basic Valkey list operations via Valkey.Glide.
/// No search module is required — this provider works with any Valkey server.
/// </para>
/// <para>
/// <strong>Data retention:</strong> Stored messages have no TTL and persist indefinitely.
/// Use <see cref="ValkeyChatHistoryProviderOptions.MaxMessages"/> to limit per-conversation storage, and <see cref="ClearMessagesAsync"/>
/// for explicit cleanup. Callers are responsible for implementing data retention policies.
/// </para>
/// <para>
/// <strong>Security considerations:</strong>
/// <list type="bullet">
/// <item><description><strong>PII and sensitive data:</strong> Chat history stored in Valkey may contain PII and sensitive
/// conversation content. Ensure the Valkey server is configured with appropriate access controls and encryption in transit
/// (TLS). The <see cref="ValkeyChatHistoryProviderOptions.MaxMessages"/> property can limit stored messages per conversation.</description></item>
/// <item><description><strong>Compromised store risks:</strong> Agent Framework does not validate or filter messages loaded
/// from the store — they are accepted as-is. If the Valkey store is compromised, adversarial content could be injected
/// into the conversation context.</description></item>
/// </list>
/// </para>
/// </remarks>
public sealed class ValkeyChatHistoryProvider : ChatHistoryProvider
{
    private readonly ProviderSessionState<State> _sessionState;
    private IReadOnlyList<string>? _stateKeys;
    private readonly IConnectionMultiplexer _connection;
    private readonly string _keyPrefix;
    private readonly int? _maxMessages;
    private readonly int? _maxMessagesToRetrieve;
    private readonly JsonSerializerOptions _jsonSerializerOptions;
    private readonly ILogger<ValkeyChatHistoryProvider>? _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="connection">An existing <see cref="IConnectionMultiplexer"/> instance.</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation.</param>
    /// <param name="options">Optional configuration options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public ValkeyChatHistoryProvider(
        IConnectionMultiplexer connection,
        Func<AgentSession?, State> stateInitializer,
        ValkeyChatHistoryProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : base(options?.ProvideOutputMessageFilter, options?.StoreInputRequestMessageFilter, options?.StoreInputResponseMessageFilter)
    {
        this._sessionState = new ProviderSessionState<State>(
            Throw.IfNull(stateInitializer),
            options?.StateKey ?? this.GetType().Name,
            options?.JsonSerializerOptions);
        this._connection = Throw.IfNull(connection);
        this._keyPrefix = options?.KeyPrefix ?? "chat_history";
        this._maxMessages = options?.MaxMessages;
        this._maxMessagesToRetrieve = options?.MaxMessagesToRetrieve;
        this._jsonSerializerOptions = options?.JsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;
        this._logger = loggerFactory?.CreateLogger<ValkeyChatHistoryProvider>();
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey];

    /// <inheritdoc />
    protected override async ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);
        cancellationToken.ThrowIfCancellationRequested();

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var db = this._connection.GetDatabase();
        var key = this.BuildKey(state);

        // Fetch only the tail when MaxMessagesToRetrieve is set [Low: avoid fetching all then trimming]
        ValkeyValue[] values;
        if (this._maxMessagesToRetrieve.HasValue)
        {
            values = await db.ListRangeAsync(key, -this._maxMessagesToRetrieve.Value, -1).ConfigureAwait(false);
        }
        else
        {
            values = await db.ListRangeAsync(key).ConfigureAwait(false);
        }

        var messages = new List<ChatMessage>(values.Length);

        foreach (var value in values)
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (value.IsNullOrEmpty)
            {
                continue;
            }

            try
            {
                var message = JsonSerializer.Deserialize(value.ToString(), this._jsonSerializerOptions.GetTypeInfo(typeof(ChatMessage))) as ChatMessage;
                if (message is not null)
                {
                    messages.Add(message);
                }
            }
            catch (JsonException ex)
            {
                // Skip malformed entries rather than crashing the session [VERIFY-002]
                this._logger?.LogWarning(ex, "ValkeyChatHistoryProvider: Skipping malformed message in conversation '{ConversationId}'.", state.ConversationId);
            }
        }

        this._logger?.LogInformation(
            "ValkeyChatHistoryProvider: Retrieved {Count} messages for conversation.",
            messages.Count);

        return messages;
    }

    /// <inheritdoc />
    protected override async ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);
        cancellationToken.ThrowIfCancellationRequested();

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var messageList = context.RequestMessages.Concat(context.ResponseMessages ?? []).ToList();
        if (messageList.Count == 0)
        {
            return;
        }

        var db = this._connection.GetDatabase();
        var key = this.BuildKey(state);

        // Batch push — single round-trip [Medium-8]
        var serialized = new ValkeyValue[messageList.Count];
        for (int i = 0; i < messageList.Count; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            serialized[i] = JsonSerializer.Serialize(messageList[i], this._jsonSerializerOptions.GetTypeInfo(typeof(ChatMessage)));
        }

        await db.ListRightPushAsync(key, serialized).ConfigureAwait(false);

        // Trim to max messages if configured
        if (this._maxMessages.HasValue)
        {
            await db.ListTrimAsync(key, -this._maxMessages.Value, -1).ConfigureAwait(false);
        }

        this._logger?.LogInformation(
            "ValkeyChatHistoryProvider: Stored {Count} messages for conversation.",
            messageList.Count);
    }

    /// <summary>
    /// Clears all messages for the specified session's conversation.
    /// </summary>
    /// <param name="session">The session containing the conversation state.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    public async Task ClearMessagesAsync(AgentSession? session, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var state = this._sessionState.GetOrInitializeState(session);
        var db = this._connection.GetDatabase();
        var key = this.BuildKey(state);
        await db.KeyDeleteAsync(key).ConfigureAwait(false);
    }

    /// <summary>
    /// Gets the count of stored messages for the specified session's conversation.
    /// </summary>
    /// <param name="session">The session containing the conversation state.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The number of stored messages.</returns>
    public async Task<long> GetMessageCountAsync(AgentSession? session, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var state = this._sessionState.GetOrInitializeState(session);
        var db = this._connection.GetDatabase();
        var key = this.BuildKey(state);
        return await db.ListLengthAsync(key).ConfigureAwait(false);
    }

    private string BuildKey(State state) => $"{this._keyPrefix}:{state.ConversationId}";

    /// <summary>
    /// Represents the per-session state of a <see cref="ValkeyChatHistoryProvider"/>.
    /// </summary>
    public sealed class State
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="State"/> class.
        /// </summary>
        /// <param name="conversationId">The unique identifier for this conversation thread.</param>
        [JsonConstructor]
        public State(string conversationId)
        {
            this.ConversationId = Throw.IfNullOrWhitespace(conversationId);
        }

        /// <summary>
        /// Gets the conversation ID associated with this state.
        /// </summary>
        public string ConversationId { get; }
    }
}
