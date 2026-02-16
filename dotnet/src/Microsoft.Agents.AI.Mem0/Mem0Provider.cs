// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Mem0;

/// <summary>
/// Provides a Mem0 backed <see cref="AIContextProvider"/> that persists conversation messages as memories
/// and retrieves related memories to augment the agent invocation context.
/// </summary>
/// <remarks>
/// The provider stores user, assistant and system messages as Mem0 memories and retrieves relevant memories
/// for new invocations using a semantic search endpoint. Retrieved memories are injected as user messages
/// to the model, prefixed by a configurable context prompt.
/// </remarks>
public sealed class Mem0Provider : AIContextProvider
{
    private const string DefaultContextPrompt = "## Memories\nConsider the following memories when answering user questions:";

    private static IEnumerable<ChatMessage> DefaultExternalOnlyFilter(IEnumerable<ChatMessage> messages)
        => messages.Where(m => m.GetAgentRequestMessageSourceType() == AgentRequestMessageSourceType.External);

    private readonly string _contextPrompt;
    private readonly bool _enableSensitiveTelemetryData;
    private readonly string _stateKey;
    private readonly Func<AgentSession?, State> _stateInitializer;
    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>> _searchInputMessageFilter;
    private readonly Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>> _storageInputMessageFilter;

    private readonly Mem0Client _client;
    private readonly ILogger<Mem0Provider>? _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="Mem0Provider"/> class.
    /// </summary>
    /// <param name="httpClient">Configured <see cref="HttpClient"/> (base address + auth).</param>
    /// <param name="stateInitializer">A delegate that initializes the provider state on the first invocation, providing the storage and search scopes.</param>
    /// <param name="options">Provider options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="httpClient"/> or <paramref name="stateInitializer"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The base address of the required mem0 service, and any authentication headers, should be set on the <paramref name="httpClient"/>
    /// already, when passed as a parameter here. E.g.:
    /// <code>
    /// using var httpClient = new HttpClient();
    /// httpClient.BaseAddress = new Uri("https://api.mem0.ai");
    /// httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Token", "&lt;Your APIKey&gt;");
    /// new Mem0Provider(httpClient);
    /// </code>
    /// </remarks>
    public Mem0Provider(HttpClient httpClient, Func<AgentSession?, State> stateInitializer, Mem0ProviderOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(httpClient);
        if (string.IsNullOrWhiteSpace(httpClient.BaseAddress?.AbsoluteUri))
        {
            throw new ArgumentException("The HttpClient BaseAddress must be set for Mem0 operations.", nameof(httpClient));
        }

        this._stateInitializer = Throw.IfNull(stateInitializer);
        this._logger = loggerFactory?.CreateLogger<Mem0Provider>();
        this._client = new Mem0Client(httpClient);

        this._contextPrompt = options?.ContextPrompt ?? DefaultContextPrompt;
        this._enableSensitiveTelemetryData = options?.EnableSensitiveTelemetryData ?? false;
        this._stateKey = options?.StateKey ?? base.StateKey;
        this._searchInputMessageFilter = options?.SearchInputMessageFilter ?? DefaultExternalOnlyFilter;
        this._storageInputMessageFilter = options?.StorageInputMessageFilter ?? DefaultExternalOnlyFilter;
    }

    /// <inheritdoc />
    public override string StateKey => this._stateKey;

    /// <summary>
    /// Gets the state from the session's StateBag, or initializes it using the StateInitializer if not present.
    /// </summary>
    /// <param name="session">The agent session containing the StateBag.</param>
    /// <returns>The provider state, or null if no session is available.</returns>
    private State? GetOrInitializeState(AgentSession? session)
    {
        if (session?.StateBag.TryGetValue<State>(this._stateKey, out var state, Mem0JsonUtilities.DefaultOptions) is true && state is not null)
        {
            return state;
        }

        state = this._stateInitializer(session);

        if (state is null
            || state.StorageScope is null
            || (state.StorageScope.AgentId is null && state.StorageScope.ThreadId is null && state.StorageScope.UserId is null && state.StorageScope.ApplicationId is null)
            || state.SearchScope is null
            || (state.SearchScope.AgentId is null && state.SearchScope.ThreadId is null && state.SearchScope.UserId is null && state.SearchScope.ApplicationId is null))
        {
            throw new InvalidOperationException("State initializer must return a non-null state with valid storage and search scopes, where at lest one scoping parameter is set for each.");
        }

        if (session is not null)
        {
            session.StateBag.SetValue(this._stateKey, state, Mem0JsonUtilities.DefaultOptions);
        }

        return state;
    }

    /// <inheritdoc />
    protected override async ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);

        var inputContext = context.AIContext;
        var state = this.GetOrInitializeState(context.Session);
        var searchScope = state?.SearchScope ?? new Mem0ProviderScope();

        string queryText = string.Join(
            Environment.NewLine,
                this._searchInputMessageFilter(inputContext.Messages ?? [])
                .Where(m => !string.IsNullOrWhiteSpace(m.Text))
                .Select(m => m.Text));

        try
        {
            var memories = (await this._client.SearchAsync(
                searchScope.ApplicationId,
                searchScope.AgentId,
                searchScope.ThreadId,
                searchScope.UserId,
                queryText,
                cancellationToken).ConfigureAwait(false)).ToList();

            var outputMessageText = memories.Count == 0
                ? null
                : $"{this._contextPrompt}\n{string.Join(Environment.NewLine, memories)}";
            var outputMessage = memories.Count == 0
                ? null
                : new ChatMessage(ChatRole.User, outputMessageText!).WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, this.GetType().FullName!);

            if (this._logger?.IsEnabled(LogLevel.Information) is true)
            {
                this._logger.LogInformation(
                    "Mem0AIContextProvider: Retrieved {Count} memories. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', ThreadId: '{ThreadId}', UserId: '{UserId}'.",
                    memories.Count,
                    searchScope.ApplicationId,
                    searchScope.AgentId,
                    searchScope.ThreadId,
                    this.SanitizeLogData(searchScope.UserId));

                if (outputMessageText is not null && this._logger.IsEnabled(LogLevel.Trace))
                {
                    this._logger.LogTrace(
                        "Mem0AIContextProvider: Search Results\nInput:{Input}\nOutput:{MessageText}\nApplicationId: '{ApplicationId}', AgentId: '{AgentId}', ThreadId: '{ThreadId}', UserId: '{UserId}'.",
                        this.SanitizeLogData(queryText),
                        this.SanitizeLogData(outputMessageText),
                        searchScope.ApplicationId,
                        searchScope.AgentId,
                        searchScope.ThreadId,
                        this.SanitizeLogData(searchScope.UserId));
                }
            }

            return new AIContext
            {
                Instructions = inputContext.Instructions,
                Messages =
                    (inputContext.Messages ?? [])
                    .Concat(outputMessage is not null ? [outputMessage] : []),
                Tools = inputContext.Tools
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
                    "Mem0AIContextProvider: Failed to search Mem0 for memories due to error. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', ThreadId: '{ThreadId}', UserId: '{UserId}'.",
                    searchScope.ApplicationId,
                    searchScope.AgentId,
                    searchScope.ThreadId,
                    this.SanitizeLogData(searchScope.UserId));
            }
            return inputContext;
        }
    }

    /// <inheritdoc />
    protected override async ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            return; // Do not update memory on failed invocations.
        }

        var state = this.GetOrInitializeState(context.Session);
        var storageScope = state?.StorageScope ?? new Mem0ProviderScope();

        try
        {
            // Persist request and response messages after invocation.
            await this.PersistMessagesAsync(
                storageScope,
                this._storageInputMessageFilter(context.RequestMessages)
                    .Concat(context.ResponseMessages ?? []),
                cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            if (this._logger?.IsEnabled(LogLevel.Error) is true)
            {
                this._logger.LogError(
                    ex,
                    "Mem0AIContextProvider: Failed to send messages to Mem0 due to error. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', ThreadId: '{ThreadId}', UserId: '{UserId}'.",
                    storageScope.ApplicationId,
                    storageScope.AgentId,
                    storageScope.ThreadId,
                    this.SanitizeLogData(storageScope.UserId));
            }
        }
    }

    /// <summary>
    /// Clears stored memories for the specified scope.
    /// </summary>
    /// <param name="session">The session containing the scope state to clear memories for.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    public Task ClearStoredMemoriesAsync(AgentSession session, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(session);
        var state = this.GetOrInitializeState(session);
        var storageScope = state?.StorageScope;

        if (storageScope is null)
        {
            return Task.CompletedTask; // Nothing to clear if there is no state.
        }

        return this._client.ClearMemoryAsync(
            storageScope.ApplicationId,
            storageScope.AgentId,
            storageScope.ThreadId,
            storageScope.UserId,
            cancellationToken);
    }

    private async Task PersistMessagesAsync(Mem0ProviderScope storageScope, IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
    {
        foreach (var message in messages)
        {
            switch (message.Role)
            {
                case ChatRole u when u == ChatRole.User:
                case ChatRole a when a == ChatRole.Assistant:
                case ChatRole s when s == ChatRole.System:
                    break;
                default:
                    continue; // ignore other roles
            }

            if (string.IsNullOrWhiteSpace(message.Text))
            {
                continue;
            }

            await this._client.CreateMemoryAsync(
                storageScope.ApplicationId,
                storageScope.AgentId,
                storageScope.ThreadId,
                storageScope.UserId,
                message.Text,
                message.Role.Value,
                cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Represents the state of a <see cref="Mem0Provider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    public sealed class State
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="State"/> class with the specified storage and search scopes.
        /// </summary>
        /// <param name="storageScope">The scope to use when storing memories.</param>
        /// <param name="searchScope">The scope to use when searching for memories. If null, the storage scope will be used for searching as well.</param>
        [JsonConstructor]
        public State(Mem0ProviderScope storageScope, Mem0ProviderScope? searchScope = null)
        {
            this.StorageScope = Throw.IfNull(storageScope);
            this.SearchScope = searchScope ?? storageScope;
        }

        /// <summary>
        /// Gets the scope used when storing memories.
        /// </summary>
        public Mem0ProviderScope StorageScope { get; }

        /// <summary>
        /// Gets the scope used when searching memories.
        /// </summary>
        public Mem0ProviderScope SearchScope { get; }
    }

    private string? SanitizeLogData(string? data) => this._enableSensitiveTelemetryData ? data : "<redacted>";
}
