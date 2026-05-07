// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Valkey;

/// <summary>
/// Provides a Valkey-backed <see cref="MessageAIContextProvider"/> that persists conversation messages
/// and retrieves related context using Valkey's native full-text search (FT.SEARCH).
/// </summary>
/// <remarks>
/// <para>
/// This provider stores user, assistant, and system messages as Valkey HASH documents and retrieves
/// relevant context for new invocations using full-text search. Retrieved memories are injected as
/// user messages to the model, prefixed by a configurable context prompt.
/// </para>
/// <para>
/// <strong>Server requirements:</strong> This provider requires valkey-search &gt;= 1.2 (ships with
/// valkey-bundle &gt;= 9.1.0) for the FT.CREATE and FT.SEARCH commands.
/// </para>
/// <para>
/// <strong>Data retention:</strong> Stored documents have no TTL and persist indefinitely.
/// Callers are responsible for implementing data retention policies (e.g., periodic cleanup)
/// to limit PII accumulation.
/// </para>
/// <para>
/// <strong>Security considerations:</strong>
/// <list type="bullet">
/// <item><description><strong>PII and sensitive data:</strong> Conversation messages are stored in Valkey
/// and may contain PII. Ensure the server is configured with appropriate access controls and TLS.</description></item>
/// <item><description><strong>Indirect prompt injection:</strong> Memories retrieved from Valkey are injected
/// into the LLM context as user messages. If the store is compromised, adversarial content could influence
/// LLM behavior.</description></item>
/// </list>
/// </para>
/// </remarks>
public sealed class ValkeyContextProvider : MessageAIContextProvider, IAsyncDisposable
{
    private const string DefaultContextPrompt = "## Memories\nConsider the following memories when answering user questions:";

    private static readonly char[] s_specialQueryChars = ['@', '!', '{', '}', '(', ')', '|', '\\', '-', '=', '~', '[', ']', '^', '"', '\'', ':', '*', '$', '>', '+', '/'];

    private readonly ProviderSessionState<State> _sessionState;
    private IReadOnlyList<string>? _stateKeys;
    private readonly IConnectionMultiplexer _connection;
    private readonly bool _ownsConnection;
    private readonly string _indexName;
    private readonly string _keyPrefix;
    private readonly string _contextPrompt;
    private readonly ILogger<ValkeyContextProvider>? _logger;
    private readonly object _indexLock = new();
    private volatile bool _indexCreated;
    private volatile bool _disposed;

    /// <summary>
    /// Gets or sets the maximum number of search results to return. Defaults to 10.
    /// </summary>
    public int MaxResults { get; set; } = 10;

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyContextProvider"/> class using a connection string.
    /// </summary>
    /// <param name="connectionString">The Valkey connection string (e.g., "localhost:6379").</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation.</param>
    /// <param name="indexName">The name of the search index. Defaults to "context_idx".</param>
    /// <param name="keyPrefix">The key prefix for stored documents. Defaults to "context:".</param>
    /// <param name="contextPrompt">The prompt to prepend to retrieved memories.</param>
    /// <param name="stateKey">An optional key for storing state in the session's StateBag.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <param name="provideInputMessageFilter">An optional filter for input messages before searching.</param>
    /// <param name="storeInputRequestMessageFilter">An optional filter for request messages before storing.</param>
    /// <param name="storeInputResponseMessageFilter">An optional filter for response messages before storing.</param>
    /// <remarks>
    /// This constructor opens a synchronous connection to Valkey. For ASP.NET Core / DI scenarios,
    /// prefer the <see cref="IConnectionMultiplexer"/> overload with a pre-connected instance to
    /// avoid blocking the thread pool.
    /// </remarks>
    public ValkeyContextProvider(
        string connectionString,
        Func<AgentSession?, State> stateInitializer,
        string indexName = "context_idx",
        string keyPrefix = "context:",
        string? contextPrompt = null,
        string? stateKey = null,
        ILoggerFactory? loggerFactory = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideInputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputRequestMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputResponseMessageFilter = null)
        : base(provideInputMessageFilter, storeInputRequestMessageFilter, storeInputResponseMessageFilter)
    {
        Throw.IfNullOrWhitespace(connectionString);
        this._sessionState = new ProviderSessionState<State>(
            ValidateStateInitializer(Throw.IfNull(stateInitializer)),
            stateKey ?? this.GetType().Name);
        this._connection = ConnectionMultiplexer.Connect(connectionString);
        this._ownsConnection = true;
        this._indexName = indexName;
        this._keyPrefix = keyPrefix;
        this._contextPrompt = contextPrompt ?? DefaultContextPrompt;
        this._logger = loggerFactory?.CreateLogger<ValkeyContextProvider>();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyContextProvider"/> class using an existing connection.
    /// </summary>
    /// <param name="connection">An existing <see cref="IConnectionMultiplexer"/> instance.</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation.</param>
    /// <param name="indexName">The name of the search index. Defaults to "context_idx".</param>
    /// <param name="keyPrefix">The key prefix for stored documents. Defaults to "context:".</param>
    /// <param name="contextPrompt">The prompt to prepend to retrieved memories.</param>
    /// <param name="stateKey">An optional key for storing state in the session's StateBag.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <param name="provideInputMessageFilter">An optional filter for input messages before searching.</param>
    /// <param name="storeInputRequestMessageFilter">An optional filter for request messages before storing.</param>
    /// <param name="storeInputResponseMessageFilter">An optional filter for response messages before storing.</param>
    public ValkeyContextProvider(
        IConnectionMultiplexer connection,
        Func<AgentSession?, State> stateInitializer,
        string indexName = "context_idx",
        string keyPrefix = "context:",
        string? contextPrompt = null,
        string? stateKey = null,
        ILoggerFactory? loggerFactory = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideInputMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputRequestMessageFilter = null,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputResponseMessageFilter = null)
        : base(provideInputMessageFilter, storeInputRequestMessageFilter, storeInputResponseMessageFilter)
    {
        this._sessionState = new ProviderSessionState<State>(
            ValidateStateInitializer(Throw.IfNull(stateInitializer)),
            stateKey ?? this.GetType().Name);
        this._connection = Throw.IfNull(connection);
        this._ownsConnection = false;
        this._indexName = indexName;
        this._keyPrefix = keyPrefix;
        this._contextPrompt = contextPrompt ?? DefaultContextPrompt;
        this._logger = loggerFactory?.CreateLogger<ValkeyContextProvider>();
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey];

    /// <inheritdoc />
    protected override async ValueTask<IEnumerable<ChatMessage>> ProvideMessagesAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);
        this.ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var scope = state.SearchScope;

        string queryText = string.Join(
            Environment.NewLine,
            context.RequestMessages
                .Where(m => !string.IsNullOrWhiteSpace(m.Text))
                .Select(m => m.Text));

        if (string.IsNullOrWhiteSpace(queryText))
        {
            return [];
        }

        try
        {
            await this.EnsureIndexAsync(cancellationToken).ConfigureAwait(false);
            var db = this._connection.GetDatabase();

            // Build filter from scope — includes thread_id for cross-scope isolation [VULN-001]
            var filterParts = new List<string>();
            if (!string.IsNullOrEmpty(scope.ApplicationId))
            {
                filterParts.Add($"@application_id:{{{EscapeTag(scope.ApplicationId)}}}");
            }

            if (!string.IsNullOrEmpty(scope.AgentId))
            {
                filterParts.Add($"@agent_id:{{{EscapeTag(scope.AgentId)}}}");
            }

            if (!string.IsNullOrEmpty(scope.UserId))
            {
                filterParts.Add($"@user_id:{{{EscapeTag(scope.UserId)}}}");
            }

            if (!string.IsNullOrEmpty(scope.ThreadId))
            {
                filterParts.Add($"@thread_id:{{{EscapeTag(scope.ThreadId)}}}");
            }

            var filterExpr = filterParts.Count > 0 ? string.Join(" ", filterParts) : "*";
            var escapedQuery = $"{filterExpr} {EscapeQuery(queryText)}";

            cancellationToken.ThrowIfCancellationRequested();

            var result = await db.ExecuteAsync(
                "FT.SEARCH",
                this._indexName,
                escapedQuery,
                "LIMIT", "0", this.MaxResults.ToString(CultureInfo.InvariantCulture)).ConfigureAwait(false);

            var memories = ParseSearchResults(result);
            var memoryTexts = memories
                .Select(m => m.TryGetValue("content", out var c) ? c : null)
                .Where(c => !string.IsNullOrEmpty(c))
                .ToList();

            this._logger?.LogDebug(
                "ValkeyContextProvider: Retrieved {Count} memories.",
                memoryTexts.Count);

            if (memoryTexts.Count == 0)
            {
                return [];
            }

            var outputText = $"{this._contextPrompt}\n{string.Join(Environment.NewLine, memoryTexts)}";
            return [new ChatMessage(ChatRole.User, outputText)];
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            // Graceful degradation: if memory search fails, the agent still works without context enrichment.
            this._logger?.LogError(ex, "ValkeyContextProvider: Failed to search for memories.");
            return [];
        }
    }

    /// <inheritdoc />
    protected override async ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);
        this.ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var scope = state.StorageScope;

        try
        {
            await this.EnsureIndexAsync(cancellationToken).ConfigureAwait(false);
            var db = this._connection.GetDatabase();

            foreach (var message in context.RequestMessages.Concat(context.ResponseMessages ?? []))
            {
                cancellationToken.ThrowIfCancellationRequested();

                if (message.Role != ChatRole.User && message.Role != ChatRole.Assistant && message.Role != ChatRole.System)
                {
                    continue;
                }

                if (string.IsNullOrWhiteSpace(message.Text))
                {
                    continue;
                }

                var docId = $"{this._keyPrefix}{Guid.NewGuid():N}";
                var entries = new HashEntry[]
                {
                    new("role", message.Role.Value),
                    new("content", message.Text),
                    new("application_id", scope.ApplicationId ?? string.Empty),
                    new("agent_id", scope.AgentId ?? string.Empty),
                    new("user_id", scope.UserId ?? string.Empty),
                    new("thread_id", scope.ThreadId ?? string.Empty),
                };

                await db.HashSetAsync(docId, entries).ConfigureAwait(false);
            }

            this._logger?.LogDebug("ValkeyContextProvider: Stored messages.");
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            // Graceful degradation: storage failure should not break the agent invocation pipeline.
            this._logger?.LogError(ex, "ValkeyContextProvider: Failed to store messages.");
        }
    }

    private async Task EnsureIndexAsync(CancellationToken cancellationToken)
    {
        if (this._indexCreated)
        {
            return;
        }

        // Minimizes redundant FT.CREATE calls across concurrent threads.
        // FT.CREATE is idempotent (caught by "Index already exists"), so concurrent calls are safe
        // but wasteful — this reduces them to typically one.
        bool needsCreate;
        lock (this._indexLock)
        {
            needsCreate = !this._indexCreated;
        }

        if (!needsCreate)
        {
            return;
        }

        cancellationToken.ThrowIfCancellationRequested();
        var db = this._connection.GetDatabase();

        try
        {
            await db.ExecuteAsync(
                "FT.CREATE",
                this._indexName,
                "ON", "HASH",
                "PREFIX", "1", this._keyPrefix,
                "SCHEMA",
                "role", "TAG",
                "content", "TEXT",
                "application_id", "TAG",
                "agent_id", "TAG",
                "user_id", "TAG",
                "thread_id", "TAG").ConfigureAwait(false);
        }
        catch (RedisServerException ex) when (ex.Message.Contains("Index already exists"))
        {
            // Index already exists — this is expected
        }

        lock (this._indexLock)
        {
            this._indexCreated = true;
        }
    }

    internal static List<Dictionary<string, string>> ParseSearchResults(RedisResult result)
    {
        var docs = new List<Dictionary<string, string>>();
        if (result.IsNull)
        {
            return docs;
        }

        var results = (RedisResult[])result!;
        if (results.Length < 2)
        {
            return docs;
        }

        // FT.SEARCH returns: [total_count, doc_id, [field, value, ...], doc_id, ...]
        for (int i = 1; i < results.Length; i += 2)
        {
            if (i + 1 >= results.Length)
            {
                break;
            }

            var fields = (RedisResult[])results[i + 1]!;
            var doc = new Dictionary<string, string>(StringComparer.Ordinal);
            for (int j = 0; j < fields.Length; j += 2)
            {
                doc[(string)fields[j]!] = (string)fields[j + 1]!;
            }

            docs.Add(doc);
        }

        return docs;
    }

    internal static string EscapeTag(string value)
    {
        return value
            .Replace("\\", "\\\\")
            .Replace("{", "\\{")
            .Replace("}", "\\}")
            .Replace("@", "\\@")
            .Replace("|", "\\|")
            .Replace("-", "\\-")
            .Replace(".", "\\.")
            .Replace(":", "\\:")
            .Replace("'", "\\'")
            .Replace("\"", "\\\"")
            .Replace(" ", "\\ ");
    }

    internal static string EscapeQuery(string text)
    {
        var escaped = new System.Text.StringBuilder(text.Length * 2);
        foreach (var ch in text)
        {
            if (Array.IndexOf(s_specialQueryChars, ch) >= 0)
            {
                escaped.Append('\\');
            }

            escaped.Append(ch);
        }

        return escaped.ToString();
    }

    private static Func<AgentSession?, State> ValidateStateInitializer(Func<AgentSession?, State> stateInitializer) =>
        session =>
        {
            var state = stateInitializer(session);
            if (state?.StorageScope is null || state.SearchScope is null)
            {
                throw new InvalidOperationException("State initializer must return a non-null state with valid storage and search scopes.");
            }

            var ss = state.StorageScope;
            var rs = state.SearchScope;
            if (ss.AgentId is null && ss.UserId is null && ss.ApplicationId is null && ss.ThreadId is null)
            {
                throw new InvalidOperationException("At least one scoping parameter (AgentId, UserId, ApplicationId, or ThreadId) must be set on StorageScope.");
            }

            if (rs.AgentId is null && rs.UserId is null && rs.ApplicationId is null && rs.ThreadId is null)
            {
                throw new InvalidOperationException("At least one scoping parameter (AgentId, UserId, ApplicationId, or ThreadId) must be set on SearchScope.");
            }

            return state;
        };

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
    /// Represents the per-session state of a <see cref="ValkeyContextProvider"/>.
    /// </summary>
    public sealed class State
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="State"/> class.
        /// </summary>
        /// <param name="storageScope">The scope to use when storing context.</param>
        /// <param name="searchScope">The scope to use when searching. If null, the storage scope is used.</param>
        public State(ValkeyProviderScope storageScope, ValkeyProviderScope? searchScope = null)
        {
            this.StorageScope = Throw.IfNull(storageScope);
            this.SearchScope = searchScope ?? storageScope;
        }

        /// <summary>
        /// Gets the scope used when storing context.
        /// </summary>
        public ValkeyProviderScope StorageScope { get; }

        /// <summary>
        /// Gets the scope used when searching context.
        /// </summary>
        public ValkeyProviderScope SearchScope { get; }
    }
}
