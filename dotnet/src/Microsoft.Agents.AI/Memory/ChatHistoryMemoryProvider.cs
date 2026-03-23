// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Linq.Expressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.VectorData;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

#pragma warning disable IDE0001 // Simplify Names - Microsoft.Extensions.Logging.LogLevel.Trace doesn't get found in net472 when removing the namespace.
/// <summary>
/// A context provider that stores all chat history in a vector store and is able to
/// retrieve related chat history later to augment the current conversation.
/// </summary>
/// <remarks>
/// <para>
/// This provider stores chat messages in a vector store and retrieves relevant previous messages
/// to provide as context during agent invocations. It uses the VectorStore and VectorStoreCollection
/// abstractions to work with any compatible vector store implementation.
/// </para>
/// <para>
/// Messages are stored during the <see cref="StoreAIContextAsync"/> method and retrieved during the
/// <see cref="ProvideAIContextAsync"/> method using semantic similarity search.
/// </para>
/// <para>
/// Behavior is configurable through <see cref="ChatHistoryMemoryProviderOptions"/>. When
/// <see cref="ChatHistoryMemoryProviderOptions.SearchBehavior.OnDemandFunctionCalling"/> is selected the provider
/// exposes a function tool that the model can invoke to retrieve relevant memories on demand instead of
/// injecting them automatically on each invocation.
/// </para>
/// <para>
/// <strong>Security considerations:</strong>
/// <list type="bullet">
/// <item><description><strong>Indirect prompt injection:</strong> Messages retrieved from the vector store via semantic search
/// are injected into the LLM context. If the vector store is compromised, adversarial content could influence LLM behavior.
/// The data returned from the store is accepted as-is without validation or sanitization.</description></item>
/// <item><description><strong>PII and sensitive data:</strong> Conversation messages (including user inputs and LLM responses)
/// are stored as vectors in the underlying store. These messages may contain PII or sensitive information. Ensure the vector
/// store is configured with appropriate access controls and encryption at rest.</description></item>
/// <item><description><strong>On-demand search tool:</strong> When using <see cref="ChatHistoryMemoryProviderOptions.SearchBehavior.OnDemandFunctionCalling"/>,
/// the AI model controls when and what to search for. The search query is AI-generated and should be treated as untrusted input
/// by the vector store implementation.</description></item>
/// <item><description><strong>Trace logging:</strong> When <see cref="Microsoft.Extensions.Logging.LogLevel.Trace"/> is enabled,
/// full search queries and results may be logged. This data may contain PII.</description></item>
/// </list>
/// </para>
/// </remarks>
public sealed class ChatHistoryMemoryProvider : MessageAIContextProvider, IDisposable
#pragma warning restore IDE0001 // Simplify Names
{
    private const string DefaultContextPrompt = "## Memories\nConsider the following memories when answering user questions:";
    private const int DefaultMaxResults = 3;
    private const string DefaultFunctionToolName = "Search";
    private const string DefaultFunctionToolDescription = "Allows searching for related previous chat history to help answer the user question.";

    private const string KeyField = "Key";
    private const string RoleField = "Role";
    private const string MessageIdField = "MessageId";
    private const string AuthorNameField = "AuthorName";
    private const string ApplicationIdField = "ApplicationId";
    private const string AgentIdField = "AgentId";
    private const string UserIdField = "UserId";
    private const string SessionIdField = "SessionId";
    private const string ContentField = "Content";
    private const string CreatedAtField = "CreatedAt";
    private const string ContentEmbeddingField = "ContentEmbedding";

    private readonly ProviderSessionState<State> _sessionState;
    private IReadOnlyList<string>? _stateKeys;

#pragma warning disable CA2213 // VectorStore is not owned by this class - caller is responsible for disposal
    private readonly VectorStore _vectorStore;
#pragma warning restore CA2213
    private readonly VectorStoreCollection<object, Dictionary<string, object?>> _collection;
    private readonly int _maxResults;
    private readonly string _contextPrompt;
    private readonly bool _enableSensitiveTelemetryData;
    private readonly ChatHistoryMemoryProviderOptions.SearchBehavior _searchTime;
    private readonly string _toolName;
    private readonly string _toolDescription;
    private readonly ILogger<ChatHistoryMemoryProvider>? _logger;

    private bool _collectionInitialized;
    private readonly SemaphoreSlim _initializationLock = new(1, 1);
    private bool _disposedValue;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryMemoryProvider"/> class.
    /// </summary>
    /// <param name="vectorStore">The vector store to use for storing and retrieving chat history.</param>
    /// <param name="collectionName">The name of the collection for storing chat history in the vector store.</param>
    /// <param name="vectorDimensions">The number of dimensions to use for the chat history vector store embeddings.</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation, providing the storage and search scopes.</param>
    /// <param name="options">Optional configuration options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="vectorStore"/> or <paramref name="stateInitializer"/> is <see langword="null"/>.</exception>
    public ChatHistoryMemoryProvider(
        VectorStore vectorStore,
        string collectionName,
        int vectorDimensions,
        Func<AgentSession?, State> stateInitializer,
        ChatHistoryMemoryProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : base(options?.SearchInputMessageFilter, options?.StorageInputRequestMessageFilter, options?.StorageInputResponseMessageFilter)
    {
        this._sessionState = new ProviderSessionState<State>(
            Throw.IfNull(stateInitializer),
            options?.StateKey ?? this.GetType().Name,
            AgentJsonUtilities.DefaultOptions);
        this._vectorStore = Throw.IfNull(vectorStore);

        options ??= new ChatHistoryMemoryProviderOptions();
        this._maxResults = options.MaxResults.HasValue ? Throw.IfLessThanOrEqual(options.MaxResults.Value, 0) : DefaultMaxResults;
        this._contextPrompt = options.ContextPrompt ?? DefaultContextPrompt;
        this._enableSensitiveTelemetryData = options.EnableSensitiveTelemetryData;
        this._searchTime = options.SearchTime;
        this._logger = loggerFactory?.CreateLogger<ChatHistoryMemoryProvider>();
        this._toolName = options.FunctionToolName ?? DefaultFunctionToolName;
        this._toolDescription = options.FunctionToolDescription ?? DefaultFunctionToolDescription;

        // Create a definition so that we can use the dimensions provided at runtime.
        var definition = new VectorStoreCollectionDefinition
        {
            Properties =
            [
                new VectorStoreKeyProperty(KeyField, typeof(Guid)),
                new VectorStoreDataProperty(RoleField, typeof(string)) { IsIndexed = true },
                new VectorStoreDataProperty(MessageIdField, typeof(string)) { IsIndexed = true },
                new VectorStoreDataProperty(AuthorNameField, typeof(string)),
                new VectorStoreDataProperty(ApplicationIdField, typeof(string)) { IsIndexed = true },
                new VectorStoreDataProperty(AgentIdField, typeof(string)) { IsIndexed = true },
                new VectorStoreDataProperty(UserIdField, typeof(string)) { IsIndexed = true },
                new VectorStoreDataProperty(SessionIdField, typeof(string)) { IsIndexed = true },
                new VectorStoreDataProperty(ContentField, typeof(string)) { IsFullTextIndexed = true },
                new VectorStoreDataProperty(CreatedAtField, typeof(string)) { IsIndexed = true },
                new VectorStoreVectorProperty(ContentEmbeddingField, typeof(string), Throw.IfLessThan(vectorDimensions, 1))
            ]
        };

        this._collection = this._vectorStore.GetDynamicCollection(Throw.IfNullOrWhitespace(collectionName), definition);
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey];

    /// <inheritdoc />
    protected override async ValueTask<AIContext> ProvideAIContextAsync(AIContextProvider.InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var searchScope = state.SearchScope;

        if (this._searchTime == ChatHistoryMemoryProviderOptions.SearchBehavior.OnDemandFunctionCalling)
        {
            Task<string> InlineSearchAsync(string userQuestion, CancellationToken ct)
                => this.SearchTextAsync(userQuestion, searchScope, ct);

            // Create on-demand search tool (only used when behavior is OnDemandFunctionCalling)
            AITool[] tools =
            [
                AIFunctionFactory.Create(
                    InlineSearchAsync,
                    name: this._toolName,
                    description: this._toolDescription)
            ];

            // Expose search tool for on-demand invocation by the model
            return new AIContext
            {
                Tools = tools
            };
        }

        return new AIContext
        {
            Messages = await this.ProvideMessagesAsync(
                new InvokingContext(context.Agent, context.Session, context.AIContext.Messages ?? []),
                cancellationToken).ConfigureAwait(false)
        };
    }

    /// <inheritdoc />
    protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        // This code path is invoked using InvokingAsync on MessageAIContextProvider, which does not support tools and instructions,
        // and OnDemandFunctionCalling requires tools.
        if (this._searchTime != ChatHistoryMemoryProviderOptions.SearchBehavior.BeforeAIInvoke)
        {
            throw new InvalidOperationException($"Using the {nameof(ChatHistoryMemoryProvider)} as a {nameof(MessageAIContextProvider)} is not supported when {nameof(ChatHistoryMemoryProviderOptions.SearchTime)} is set to {ChatHistoryMemoryProviderOptions.SearchBehavior.OnDemandFunctionCalling}.");
        }

        return base.InvokingCoreAsync(context, cancellationToken);
    }

    /// <inheritdoc />
    protected override async ValueTask<IEnumerable<ChatMessage>> ProvideMessagesAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var searchScope = state.SearchScope;

        try
        {
            // Get the text from the current request messages
            var requestText = string.Join("\n",
                (context.RequestMessages ?? [])
                .Where(m => m != null && !string.IsNullOrWhiteSpace(m.Text))
                .Select(m => m.Text));

            if (string.IsNullOrWhiteSpace(requestText))
            {
                return [];
            }

            // Search for relevant chat history
            var contextText = await this.SearchTextAsync(requestText, searchScope, cancellationToken).ConfigureAwait(false);

            if (string.IsNullOrWhiteSpace(contextText))
            {
                return [];
            }

            return [new ChatMessage(ChatRole.User, contextText)];
        }
        catch (Exception ex)
        {
            if (this._logger?.IsEnabled(LogLevel.Error) is true)
            {
                this._logger.LogError(
                    ex,
                    "ChatHistoryMemoryProvider: Failed to search for chat history due to error. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', SessionId: '{SessionId}', UserId: '{UserId}'.",
                    searchScope.ApplicationId,
                    searchScope.AgentId,
                    searchScope.SessionId,
                    this.SanitizeLogData(searchScope.UserId));
            }

            return [];
        }
    }

    /// <inheritdoc />
    protected override async ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        var state = this._sessionState.GetOrInitializeState(context.Session);
        var storageScope = state.StorageScope;

        try
        {
            // Ensure the collection is initialized
            var collection = await this.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);

            List<Dictionary<string, object?>> itemsToStore = context.RequestMessages
                .Concat(context.ResponseMessages ?? [])
                .Select(message => new Dictionary<string, object?>
                {
                    [KeyField] = Guid.NewGuid(),
                    [RoleField] = message.Role.ToString(),
                    [MessageIdField] = message.MessageId,
                    [AuthorNameField] = message.AuthorName,
                    [ApplicationIdField] = storageScope.ApplicationId,
                    [AgentIdField] = storageScope.AgentId,
                    [UserIdField] = storageScope.UserId,
                    [SessionIdField] = storageScope.SessionId,
                    [ContentField] = message.Text,
                    [CreatedAtField] = message.CreatedAt?.ToString("O") ?? DateTimeOffset.UtcNow.ToString("O"),
                    [ContentEmbeddingField] = message.Text,
                })
                .ToList();

            if (itemsToStore.Count > 0)
            {
                await collection.UpsertAsync(itemsToStore, cancellationToken).ConfigureAwait(false);
            }
        }
        catch (Exception ex)
        {
            if (this._logger?.IsEnabled(LogLevel.Error) is true)
            {
                this._logger.LogError(
                    ex,
                    "ChatHistoryMemoryProvider: Failed to add messages to chat history vector store due to error. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', SessionId: '{SessionId}', UserId: '{UserId}'.",
                    storageScope.ApplicationId,
                    storageScope.AgentId,
                    storageScope.SessionId,
                    this.SanitizeLogData(storageScope.UserId));
            }
        }
    }

    /// <summary>
    /// Function callable by the AI model (when enabled) to perform an ad-hoc chat history search.
    /// </summary>
    /// <param name="userQuestion">The query text.</param>
    /// <param name="searchScope">The scope to filter search results with.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Formatted search results (may be empty).</returns>
    private async Task<string> SearchTextAsync(string userQuestion, ChatHistoryMemoryProviderScope searchScope, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(userQuestion))
        {
            return string.Empty;
        }

        var results = await this.SearchChatHistoryAsync(userQuestion, searchScope, this._maxResults, cancellationToken).ConfigureAwait(false);
        if (!results.Any())
        {
            return string.Empty;
        }

        // Format the results as a single context message
        var outputResultsText = string.Join("\n", results.Select(x => (string?)x[ContentField]).Where(c => !string.IsNullOrWhiteSpace(c)));
        if (string.IsNullOrWhiteSpace(outputResultsText))
        {
            return string.Empty;
        }

        var formatted = $"{this._contextPrompt}\n{outputResultsText}";

        if (this._logger?.IsEnabled(LogLevel.Trace) is true)
        {
            this._logger.LogTrace(
                "ChatHistoryMemoryProvider: Search Results\nInput:{Input}\nOutput:{MessageText}\n ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', SessionId: '{SessionId}', UserId: '{UserId}'.",
                this.SanitizeLogData(userQuestion),
                this.SanitizeLogData(formatted),
                searchScope.ApplicationId,
                searchScope.AgentId,
                searchScope.SessionId,
                this.SanitizeLogData(searchScope.UserId));
        }

        return formatted;
    }

    /// <summary>
    /// Searches for relevant chat history items based on the provided query text.
    /// </summary>
    /// <param name="queryText">The text to search for.</param>
    /// <param name="searchScope">The scope to filter search results with.</param>
    /// <param name="top">The maximum number of results to return.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A list of relevant chat history items.</returns>
    private async Task<IEnumerable<Dictionary<string, object?>>> SearchChatHistoryAsync(
        string queryText,
        ChatHistoryMemoryProviderScope searchScope,
        int top,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(queryText))
        {
            return [];
        }

        var collection = await this.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);

        string? applicationId = searchScope.ApplicationId;
        string? agentId = searchScope.AgentId;
        string? userId = searchScope.UserId;
        string? sessionId = searchScope.SessionId;

        // Build a combined filter using a single shared parameter to avoid expression tree
        // scoping issues when multiple filters are combined with AndAlso.
        ParameterExpression parameter = Expression.Parameter(typeof(Dictionary<string, object?>), "x");
        Expression? filterBody = null;

        if (applicationId != null)
        {
            filterBody = RebindFilterBody(x => (string?)x[ApplicationIdField] == applicationId, parameter);
        }

        if (agentId != null)
        {
            Expression body = RebindFilterBody(x => (string?)x[AgentIdField] == agentId, parameter);
            filterBody = filterBody == null ? body : Expression.AndAlso(filterBody, body);
        }

        if (userId != null)
        {
            Expression body = RebindFilterBody(x => (string?)x[UserIdField] == userId, parameter);
            filterBody = filterBody == null ? body : Expression.AndAlso(filterBody, body);
        }

        if (sessionId != null)
        {
            Expression body = RebindFilterBody(x => (string?)x[SessionIdField] == sessionId, parameter);
            filterBody = filterBody == null ? body : Expression.AndAlso(filterBody, body);
        }

        Expression<Func<Dictionary<string, object?>, bool>>? filter = filterBody != null
            ? Expression.Lambda<Func<Dictionary<string, object?>, bool>>(filterBody, parameter)
            : null;

        // Use search to find relevant messages
        var searchResults = collection.SearchAsync(
            queryText,
            top,
            options: new()
            {
                Filter = filter
            },
            cancellationToken: cancellationToken);

        var results = new List<Dictionary<string, object?>>();
        await foreach (var result in searchResults.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            results.Add(result.Record);
        }

        if (this._logger?.IsEnabled(LogLevel.Information) is true)
        {
            this._logger.LogInformation(
                "ChatHistoryMemoryProvider: Retrieved {Count} search results. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', SessionId: '{SessionId}', UserId: '{UserId}'.",
                results.Count,
                searchScope.ApplicationId,
                searchScope.AgentId,
                searchScope.SessionId,
                this.SanitizeLogData(searchScope.UserId));
        }

        return results;
    }

    /// <summary>
    /// Ensures the collection exists in the vector store, creating it if necessary.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The vector store collection.</returns>
    private async Task<VectorStoreCollection<object, Dictionary<string, object?>>> EnsureCollectionExistsAsync(
        CancellationToken cancellationToken = default)
    {
        if (this._collectionInitialized)
        {
            return this._collection;
        }

        await this._initializationLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (this._collectionInitialized)
            {
                return this._collection;
            }

            await this._collection.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);
            this._collectionInitialized = true;

            return this._collection;
        }
        finally
        {
            this._initializationLock.Release();
        }
    }

    /// <inheritdoc/>
    private void Dispose(bool disposing)
    {
        if (!this._disposedValue)
        {
            if (disposing)
            {
                this._initializationLock.Dispose();
                this._collection?.Dispose();
            }

            this._disposedValue = true;
        }
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        // Do not change this code. Put cleanup code in 'Dispose(bool disposing)' method
        this.Dispose(disposing: true);
        GC.SuppressFinalize(this);
    }

    private string? SanitizeLogData(string? data) => this._enableSensitiveTelemetryData ? data : "<redacted>";

    /// <summary>
    /// Rebinds a filter expression's body to use the specified shared parameter,
    /// replacing the original lambda parameter so that multiple filters can be safely
    /// combined with <see cref="Expression.AndAlso(Expression, Expression)"/>.
    /// </summary>
    private static Expression RebindFilterBody(
        Expression<Func<Dictionary<string, object?>, bool>> filter,
        ParameterExpression sharedParameter)
    {
        return new ParameterReplacer(filter.Parameters[0], sharedParameter).Visit(filter.Body);
    }

    /// <summary>
    /// An <see cref="ExpressionVisitor"/> that replaces one <see cref="ParameterExpression"/> with another.
    /// </summary>
    private sealed class ParameterReplacer(ParameterExpression original, ParameterExpression replacement) : ExpressionVisitor
    {
        protected override Expression VisitParameter(ParameterExpression node)
            => node == original ? replacement : base.VisitParameter(node);
    }

    /// <summary>
    /// Represents the state of a <see cref="ChatHistoryMemoryProvider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    public sealed class State
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="State"/> class with the specified storage and search scopes.
        /// </summary>
        /// <param name="storageScope">The scope to use when storing chat history messages.</param>
        /// <param name="searchScope">The scope to use when searching for relevant chat history messages. If null, the storage scope will be used for searching as well.</param>
        public State(ChatHistoryMemoryProviderScope storageScope, ChatHistoryMemoryProviderScope? searchScope = null)
        {
            this.StorageScope = Throw.IfNull(storageScope);
            this.SearchScope = searchScope ?? storageScope;
        }

        /// <summary>
        /// Gets or sets the scope used when storing chat history messages.
        /// </summary>
        public ChatHistoryMemoryProviderScope StorageScope { get; }

        /// <summary>
        /// Gets or sets the scope used when searching chat history messages.
        /// </summary>
        public ChatHistoryMemoryProviderScope SearchScope { get; }
    }
}
