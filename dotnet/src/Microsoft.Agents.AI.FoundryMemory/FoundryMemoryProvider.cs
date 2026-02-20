// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Provides an Azure AI Foundry Memory backed <see cref="AIContextProvider"/> that persists conversation messages as memories
/// and retrieves related memories to augment the agent invocation context.
/// </summary>
/// <remarks>
/// The provider stores user, assistant and system messages as Foundry memories and retrieves relevant memories
/// for new invocations using the memory search endpoint. Retrieved memories are injected as user messages
/// to the model, prefixed by a configurable context prompt.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FoundryMemoryProvider : AIContextProvider
{
    private const string DefaultContextPrompt = "## Memories\nConsider the following memories when answering user questions:";

    private readonly ProviderSessionState<State> _sessionState;
    private readonly string _contextPrompt;
    private readonly string _memoryStoreName;
    private readonly int _maxMemories;
    private readonly int _updateDelay;
    private readonly bool _enableSensitiveTelemetryData;

    private readonly AIProjectClient _client;
    private readonly ILogger<FoundryMemoryProvider>? _logger;

    private string? _lastPendingUpdateId;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryMemoryProvider"/> class.
    /// </summary>
    /// <param name="client">The Azure AI Project client configured for your Foundry project.</param>
    /// <param name="memoryStoreName">The name of the memory store in Azure AI Foundry.</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation, providing the scope for memory storage and retrieval.</param>
    /// <param name="options">Provider options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="stateInitializer"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="memoryStoreName"/> is null or whitespace.</exception>
    public FoundryMemoryProvider(
        AIProjectClient client,
        string memoryStoreName,
        Func<AgentSession?, State> stateInitializer,
        FoundryMemoryProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : base(options?.SearchInputMessageFilter, options?.StorageInputMessageFilter)
    {
        Throw.IfNull(client);
        Throw.IfNullOrWhitespace(memoryStoreName);

        this._sessionState = new ProviderSessionState<State>(
            ValidateStateInitializer(Throw.IfNull(stateInitializer)),
            options?.StateKey ?? this.GetType().Name,
            FoundryMemoryJsonUtilities.DefaultOptions);

        FoundryMemoryProviderOptions effectiveOptions = options ?? new FoundryMemoryProviderOptions();

        this._logger = loggerFactory?.CreateLogger<FoundryMemoryProvider>();
        this._client = client;

        this._contextPrompt = effectiveOptions.ContextPrompt ?? DefaultContextPrompt;
        this._memoryStoreName = memoryStoreName;
        this._maxMemories = effectiveOptions.MaxMemories;
        this._updateDelay = effectiveOptions.UpdateDelay;
        this._enableSensitiveTelemetryData = effectiveOptions.EnableSensitiveTelemetryData;
    }

    /// <inheritdoc />
    public override string StateKey => this._sessionState.StateKey;

    private static Func<AgentSession?, State> ValidateStateInitializer(Func<AgentSession?, State> stateInitializer) =>
        session =>
        {
            State state = stateInitializer(session);

            if (state is null)
            {
                throw new InvalidOperationException("State initializer must return a non-null state.");
            }

            return state;
        };

    /// <inheritdoc />
    protected override async ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);

        State state = this._sessionState.GetOrInitializeState(context.Session);
        FoundryMemoryProviderScope scope = state.Scope;

        List<ResponseItem> messageItems = (context.AIContext.Messages ?? [])
            .Where(m => !string.IsNullOrWhiteSpace(m.Text))
            .Select(m => (ResponseItem)ToResponseItem(m.Role, m.Text!))
            .ToList();

        if (messageItems.Count == 0)
        {
            return new AIContext();
        }

        try
        {
            MemorySearchOptions searchOptions = new(scope.Scope)
            {
                ResultOptions = new MemorySearchResultOptions { MaxMemories = this._maxMemories }
            };

            foreach (ResponseItem item in messageItems)
            {
                searchOptions.Items.Add(item);
            }

            ClientResult<MemoryStoreSearchResponse> result = await this._client.MemoryStores.SearchMemoriesAsync(
                this._memoryStoreName,
                searchOptions,
                cancellationToken).ConfigureAwait(false);

            MemoryStoreSearchResponse response = result.Value;

            List<string> memories = response.Memories
                .Select(m => m.MemoryItem?.Content ?? string.Empty)
                .Where(c => !string.IsNullOrWhiteSpace(c))
                .ToList();

            string? outputMessageText = memories.Count == 0
                ? null
                : $"{this._contextPrompt}\n{string.Join(Environment.NewLine, memories)}";

            if (this._logger?.IsEnabled(LogLevel.Information) is true)
            {
                this._logger.LogInformation(
                    "FoundryMemoryProvider: Retrieved {Count} memories. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                    memories.Count,
                    this._memoryStoreName,
                    this.SanitizeLogData(scope.Scope));

                if (outputMessageText is not null && this._logger.IsEnabled(LogLevel.Trace))
                {
                    this._logger.LogTrace(
                        "FoundryMemoryProvider: Search Results\nOutput:{MessageText}\nMemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                        this.SanitizeLogData(outputMessageText),
                        this._memoryStoreName,
                        this.SanitizeLogData(scope.Scope));
                }
            }

            return new AIContext
            {
                Messages = [new ChatMessage(ChatRole.User, outputMessageText)]
            };
        }
        catch (ArgumentException)
        {
            throw;
        }
        catch (Exception ex)
        {
            if (this._logger?.IsEnabled(LogLevel.Error) is true)
            {
                this._logger.LogError(
                    ex,
                    "FoundryMemoryProvider: Failed to search for memories due to error. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                    this._memoryStoreName,
                    this.SanitizeLogData(scope.Scope));
            }

            return new AIContext();
        }
    }

    /// <inheritdoc />
    protected override async ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        State state = this._sessionState.GetOrInitializeState(context.Session);
        FoundryMemoryProviderScope scope = state.Scope;

        try
        {
            List<ResponseItem> messageItems = context.RequestMessages
                .Concat(context.ResponseMessages ?? [])
                .Where(m => IsAllowedRole(m.Role) && !string.IsNullOrWhiteSpace(m.Text))
                .Select(m => (ResponseItem)ToResponseItem(m.Role, m.Text!))
                .ToList();

            if (messageItems.Count == 0)
            {
                return;
            }

            MemoryUpdateOptions updateOptions = new(scope.Scope)
            {
                UpdateDelay = this._updateDelay
            };

            foreach (ResponseItem item in messageItems)
            {
                updateOptions.Items.Add(item);
            }

            ClientResult<MemoryUpdateResult> result = await this._client.MemoryStores.UpdateMemoriesAsync(
                this._memoryStoreName,
                updateOptions,
                cancellationToken).ConfigureAwait(false);

            MemoryUpdateResult response = result.Value;

            if (response.UpdateId is not null)
            {
                Interlocked.Exchange(ref this._lastPendingUpdateId, response.UpdateId);
            }

            if (this._logger?.IsEnabled(LogLevel.Information) is true)
            {
                this._logger.LogInformation(
                    "FoundryMemoryProvider: Sent {Count} messages to update memories. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}', UpdateId: '{UpdateId}'.",
                    messageItems.Count,
                    this._memoryStoreName,
                    this.SanitizeLogData(scope.Scope),
                    response.UpdateId);
            }
        }
        catch (Exception ex)
        {
            if (this._logger?.IsEnabled(LogLevel.Error) is true)
            {
                this._logger.LogError(
                    ex,
                    "FoundryMemoryProvider: Failed to send messages to update memories due to error. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                    this._memoryStoreName,
                    this.SanitizeLogData(scope.Scope));
            }
        }
    }

    /// <summary>
    /// Ensures all stored memories for the configured scope are deleted.
    /// This method handles cases where the scope doesn't exist (no memories stored yet).
    /// </summary>
    /// <param name="session">The session containing the scope state to clear memories for.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    public async Task EnsureStoredMemoriesDeletedAsync(AgentSession session, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(session);
        State state = this._sessionState.GetOrInitializeState(session);
        FoundryMemoryProviderScope scope = state.Scope;

        try
        {
            await this._client.MemoryStores.DeleteScopeAsync(this._memoryStoreName, scope.Scope, cancellationToken).ConfigureAwait(false);

            if (this._logger?.IsEnabled(LogLevel.Information) is true)
            {
                this._logger.LogInformation(
                    "FoundryMemoryProvider: Deleted stored memories for scope. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                    this._memoryStoreName,
                    this.SanitizeLogData(scope.Scope));
            }
        }
        catch (ClientResultException ex) when (ex.Status == 404)
        {
            // Scope doesn't exist (no memories stored yet), nothing to delete
            if (this._logger?.IsEnabled(LogLevel.Debug) is true)
            {
                this._logger.LogDebug(
                    "FoundryMemoryProvider: No memories to delete for scope. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                    this._memoryStoreName,
                    this.SanitizeLogData(scope.Scope));
            }
        }
    }

    /// <summary>
    /// Ensures the memory store exists, creating it if necessary.
    /// </summary>
    /// <param name="chatModel">The deployment name of the chat model for memory processing.</param>
    /// <param name="embeddingModel">The deployment name of the embedding model for memory search.</param>
    /// <param name="description">Optional description for the memory store.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    public async Task EnsureMemoryStoreCreatedAsync(
        string chatModel,
        string embeddingModel,
        string? description = null,
        CancellationToken cancellationToken = default)
    {
        bool created = await this._client.CreateMemoryStoreIfNotExistsAsync(
            this._memoryStoreName,
            description,
            chatModel,
            embeddingModel,
            cancellationToken).ConfigureAwait(false);

        if (created)
        {
            if (this._logger?.IsEnabled(LogLevel.Information) is true)
            {
                this._logger.LogInformation(
                    "FoundryMemoryProvider: Created memory store '{MemoryStoreName}'.",
                    this._memoryStoreName);
            }
        }
        else
        {
            if (this._logger?.IsEnabled(LogLevel.Debug) is true)
            {
                this._logger.LogDebug(
                    "FoundryMemoryProvider: Memory store '{MemoryStoreName}' already exists.",
                    this._memoryStoreName);
            }
        }
    }

    /// <summary>
    /// Waits for all pending memory update operations to complete.
    /// </summary>
    /// <remarks>
    /// Memory extraction in Azure AI Foundry is asynchronous. This method polls the latest pending update
    /// and returns when it has completed, failed, or been superseded. Since updates are processed in order,
    /// completion of the latest update implies all prior updates have also been processed.
    /// </remarks>
    /// <param name="pollingInterval">The interval between status checks. Defaults to 5 seconds.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <exception cref="InvalidOperationException">Thrown if the update operation failed.</exception>
    public async Task WhenUpdatesCompletedAsync(
        TimeSpan? pollingInterval = null,
        CancellationToken cancellationToken = default)
    {
        string? updateId = Volatile.Read(ref this._lastPendingUpdateId);
        if (updateId is null)
        {
            return;
        }

        TimeSpan interval = pollingInterval ?? TimeSpan.FromSeconds(5);
        await this.WaitForUpdateAsync(updateId, interval, cancellationToken).ConfigureAwait(false);

        // Only clear the pending update ID after successful completion
        Interlocked.CompareExchange(ref this._lastPendingUpdateId, null, updateId);
    }

    private async Task WaitForUpdateAsync(string updateId, TimeSpan interval, CancellationToken cancellationToken)
    {
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();

            ClientResult<MemoryUpdateResult> result = await this._client.MemoryStores.GetUpdateResultAsync(
                this._memoryStoreName,
                updateId,
                cancellationToken).ConfigureAwait(false);

            MemoryUpdateResult response = result.Value;
            MemoryStoreUpdateStatus status = response.Status;

            if (this._logger?.IsEnabled(LogLevel.Debug) is true)
            {
                this._logger.LogDebug(
                    "FoundryMemoryProvider: Update status for '{UpdateId}': {Status}",
                    updateId,
                    status);
            }

            if (status == MemoryStoreUpdateStatus.Completed || status == MemoryStoreUpdateStatus.Superseded)
            {
                return;
            }

            if (status == MemoryStoreUpdateStatus.Failed)
            {
                throw new InvalidOperationException($"Memory update operation '{updateId}' failed: {response.ErrorDetails}");
            }

            if (status == MemoryStoreUpdateStatus.Queued || status == MemoryStoreUpdateStatus.InProgress)
            {
                await Task.Delay(interval, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                throw new InvalidOperationException($"Unknown update status '{status}' for update '{updateId}'.");
            }
        }
    }

    private static MessageResponseItem ToResponseItem(ChatRole role, string text)
    {
        if (role == ChatRole.Assistant)
        {
            return ResponseItem.CreateAssistantMessageItem(text);
        }

        if (role == ChatRole.System)
        {
            return ResponseItem.CreateSystemMessageItem(text);
        }

        return ResponseItem.CreateUserMessageItem(text);
    }

    private static bool IsAllowedRole(ChatRole role) =>
        role == ChatRole.User || role == ChatRole.Assistant || role == ChatRole.System;

    private string? SanitizeLogData(string? data) => this._enableSensitiveTelemetryData ? data : "<redacted>";

    /// <summary>
    /// Represents the state of a <see cref="FoundryMemoryProvider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    public sealed class State
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="State"/> class with the specified scope.
        /// </summary>
        /// <param name="scope">The scope to use for memory storage and retrieval.</param>
        [JsonConstructor]
        public State(FoundryMemoryProviderScope scope)
        {
            this.Scope = Throw.IfNull(scope);
        }

        /// <summary>
        /// Gets the scope used for memory storage and retrieval.
        /// </summary>
        public FoundryMemoryProviderScope Scope { get; }
    }
}
