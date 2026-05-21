// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Valkey;

/// <summary>
/// Provides a Valkey-backed implementation of <see cref="ChatHistoryProvider"/> for persistent chat history storage.
/// </summary>
/// <remarks>
/// <para>
/// Uses basic Valkey list operations via StackExchange.Redis (protocol-compatible with Valkey).
/// No search module is required — this provider works with any Valkey or Redis OSS server.
/// </para>
/// <para>
/// <strong>Data retention:</strong> Stored messages have no TTL and persist indefinitely.
/// Use <see cref="MaxMessages"/> to limit per-conversation storage, and <see cref="ClearMessagesAsync"/>
/// for explicit cleanup. Callers are responsible for implementing data retention policies.
/// </para>
/// <para>
/// <strong>Security considerations:</strong>
/// <list type="bullet">
/// <item><description><strong>PII and sensitive data:</strong> Chat history stored in Valkey may contain PII and sensitive
/// conversation content. Ensure the Valkey server is configured with appropriate access controls and encryption in transit
/// (TLS). The <see cref="MaxMessages"/> property can limit stored messages per conversation.</description></item>
/// <item><description><strong>Compromised store risks:</strong> Agent Framework does not validate or filter messages loaded
/// from the store — they are accepted as-is. If the Valkey store is compromised, adversarial content could be injected
/// into the conversation context.</description></item>
/// </list>
/// </para>
/// </remarks>
[RequiresUnreferencedCode("The ValkeyChatHistoryProvider uses JSON serialization which is incompatible with trimming.")]
[RequiresDynamicCode("The ValkeyChatHistoryProvider uses JSON serialization which is incompatible with NativeAOT.")]
public sealed class ValkeyChatHistoryProvider : ChatHistoryProvider, IAsyncDisposable
{
    private readonly ProviderSessionState<State> _sessionState;
    private IReadOnlyList<string>? _stateKeys;
    private readonly IConnectionMultiplexer _connection;
    private readonly bool _ownsConnection;
    private readonly string _keyPrefix;
    private readonly ILogger<ValkeyChatHistoryProvider>? _logger;
    private volatile bool _disposed;

    /// <summary>
    /// Gets or sets the maximum number of messages to retain per conversation.
    /// When exceeded, oldest messages are automatically trimmed. Null means unlimited.
    /// </summary>
    public int? MaxMessages { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of messages to retrieve from the provider.
    /// Null means no limit.
    /// </summary>
    public int? MaxMessagesToRetrieve { get; set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyChatHistoryProvider"/> class using a connection string.
    /// </summary>
    /// <param name="connectionString">The Valkey connection string (e.g., "localhost:6379").</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation.</param>
    /// <param name="keyPrefix">Prefix for Valkey keys. Defaults to "chat_history".</param>
    /// <param name="stateKey">An optional key for storing state in the session's StateBag.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <param name="provideOutputMessageFilter">An optional filter for messages when retrieving from history.</param>
    /// <param name="storeInputRequestMessageFilter">An optional filter for request messages before storing.</param>
    /// <param name="storeInputResponseMessageFilter">An optional filter for response messages before storing.</param>
    /// <remarks>
    /// This constructor opens a synchronous connection to Valkey. For ASP.NET Core / DI scenarios,
    /// prefer the <see cref="IConnectionMultiplexer"/> overload with a pre-connected instance to
    /// avoid blocking the thread pool.
    /// </remarks>
    public ValkeyChatHistoryProvider(
        string connectionString,
        Func<AgentSession?, State> stateInitializer,
        string keyPrefix = "chat_history",
        string? stateKey = null,
        ILoggerFactory? loggerFactory = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideOutputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputRequestMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputResponseMessageFilter = null)
        : base(provideOutputMessageFilter, storeInputRequestMessageFilter, storeInputResponseMessageFilter)
    {
        Throw.IfNullOrWhitespace(connectionString);
        this._sessionState = new ProviderSessionState<State>(
            Throw.IfNull(stateInitializer),
            stateKey ?? this.GetType().Name);
        this._connection = ConnectionMultiplexer.Connect(connectionString);
        this._ownsConnection = true;
        this._keyPrefix = keyPrefix;
        this._logger = loggerFactory?.CreateLogger<ValkeyChatHistoryProvider>();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyChatHistoryProvider"/> class using an existing connection.
    /// </summary>
    /// <param name="connection">An existing <see cref="IConnectionMultiplexer"/> instance.</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation.</param>
    /// <param name="keyPrefix">Prefix for Valkey keys. Defaults to "chat_history".</param>
    /// <param name="stateKey">An optional key for storing state in the session's StateBag.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <param name="provideOutputMessageFilter">An optional filter for messages when retrieving from history.</param>
    /// <param name="storeInputRequestMessageFilter">An optional filter for request messages before storing.</param>
    /// <param name="storeInputResponseMessageFilter">An optional filter for response messages before storing.</param>
    public ValkeyChatHistoryProvider(
        IConnectionMultiplexer connection,
        Func<AgentSession?, State> stateInitializer,
        string keyPrefix = "chat_history",
        string? stateKey = null,
        ILoggerFactory? loggerFactory = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideOutputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputRequestMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputResponseMessageFilter = null)
        : base(provideOutputMessageFilter, storeInputRequestMessageFilter, storeInputResponseMessageFilter)
    {
        this._sessionState = new ProviderSessionState<State>(
            Throw.IfNull(stateInitializer),
            stateKey ?? this.GetType().Name);
        this._connection = Throw.IfNull(connection);
        this._ownsConnection = false;
        this._keyPrefix = keyPrefix;
        this._logger = loggerFactory?.CreateLogger<ValkeyChatHistoryProvider>();
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey];

    /// <inheritdoc />
    protected override async ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);
        this.ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var db = this._connection.GetDatabase();
        var key = this.BuildKey(state);

        // Fetch only the tail when MaxMessagesToRetrieve is set [Low: avoid fetching all then trimming]
        RedisValue[] values;
        if (this.MaxMessagesToRetrieve.HasValue)
        {
            values = await db.ListRangeAsync(key, -this.MaxMessagesToRetrieve.Value, -1).ConfigureAwait(false);
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
                var message = JsonSerializer.Deserialize<ChatMessage>(value.ToString());
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

        this._logger?.LogDebug(
            "ValkeyChatHistoryProvider: Retrieved {Count} messages for conversation.",
            messages.Count);

        return messages;
    }

    /// <inheritdoc />
    protected override async ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);
        this.ThrowIfDisposed();
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
        var serialized = new RedisValue[messageList.Count];
        for (int i = 0; i < messageList.Count; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            serialized[i] = JsonSerializer.Serialize(messageList[i]);
        }

        await db.ListRightPushAsync(key, serialized).ConfigureAwait(false);

        // Always trim when MaxMessages is set — LTRIM is a no-op when the list is within bounds,
        // and this avoids a TOCTOU race between LLEN and LTRIM.
        if (this.MaxMessages.HasValue)
        {
            await db.ListTrimAsync(key, -this.MaxMessages.Value, -1).ConfigureAwait(false);
        }

        this._logger?.LogDebug(
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
        this.ThrowIfDisposed();
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
        this.ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();
        var state = this._sessionState.GetOrInitializeState(session);
        var db = this._connection.GetDatabase();
        var key = this.BuildKey(state);
        return await db.ListLengthAsync(key).ConfigureAwait(false);
    }

    private string BuildKey(State state) => $"{this._keyPrefix}:{state.ConversationId}";

    private void ThrowIfDisposed()
    {
#if NET8_0_OR_GREATER
        ObjectDisposedException.ThrowIf(this._disposed, this);
#else
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().Name);
        }
#endif
    }

    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;

        if (this._ownsConnection)
        {
            await this._connection.CloseAsync().ConfigureAwait(false);
            this._connection.Dispose();
        }
    }

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
