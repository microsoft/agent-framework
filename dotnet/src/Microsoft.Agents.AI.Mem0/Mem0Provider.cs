// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
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

    private readonly string _contextPrompt;
    private readonly bool _enableSensitiveTelemetryData;

    private readonly Mem0Client _client;
    private readonly ILogger<Mem0Provider>? _logger;

    private readonly Mem0ProviderScope _storageScope;
    private readonly Mem0ProviderScope _searchScope;

    /// <summary>
    /// Initializes a new instance of the <see cref="Mem0Provider"/> class.
    /// </summary>
    /// <param name="httpClient">Configured <see cref="HttpClient"/> (base address + auth).</param>
    /// <param name="storageScope">Optional values to scope the memory storage with.</param>
    /// <param name="searchScope">Optional values to scope the memory search with. Defaults to <paramref name="storageScope"/> if not provided.</param>
    /// <param name="options">Provider options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <remarks>
    /// The base address of the required mem0 service, and any authentication headers, should be set on the <paramref name="httpClient"/>
    /// already, when passed as a parameter here. E.g.:
    /// <code>
    /// using var httpClient = new HttpClient();
    /// httpClient.BaseAddress = new Uri("https://api.mem0.ai");
    /// httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Token", "&lt;Your APIKey&gt;");
    /// new Mem0AIContextProvider(httpClient);
    /// </code>
    /// </remarks>
    public Mem0Provider(HttpClient httpClient, Mem0ProviderScope storageScope, Mem0ProviderScope? searchScope = null, Mem0ProviderOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        if (string.IsNullOrWhiteSpace(httpClient.BaseAddress?.AbsoluteUri))
        {
            throw new ArgumentException("The HttpClient BaseAddress must be set for Mem0 operations.", nameof(httpClient));
        }

        this._logger = loggerFactory?.CreateLogger<Mem0Provider>();
        this._client = new Mem0Client(httpClient);

        this._contextPrompt = options?.ContextPrompt ?? DefaultContextPrompt;
        this._enableSensitiveTelemetryData = options?.EnableSensitiveTelemetryData ?? false;
        this._storageScope = new Mem0ProviderScope(Throw.IfNull(storageScope));
        this._searchScope = searchScope ?? storageScope;

        if (string.IsNullOrWhiteSpace(this._storageScope.ApplicationId)
            && string.IsNullOrWhiteSpace(this._storageScope.AgentId)
            && string.IsNullOrWhiteSpace(this._storageScope.ThreadId)
            && string.IsNullOrWhiteSpace(this._storageScope.UserId))
        {
            throw new ArgumentException("At least one of ApplicationId, AgentId, ThreadId, or UserId must be provided for the storage scope.");
        }

        if (string.IsNullOrWhiteSpace(this._searchScope.ApplicationId)
            && string.IsNullOrWhiteSpace(this._searchScope.AgentId)
            && string.IsNullOrWhiteSpace(this._searchScope.ThreadId)
            && string.IsNullOrWhiteSpace(this._searchScope.UserId))
        {
            throw new ArgumentException("At least one of ApplicationId, AgentId, ThreadId, or UserId must be provided for the search scope.");
        }
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="Mem0Provider"/> class, with existing state from a serialized JSON element.
    /// </summary>
    /// <param name="httpClient">Configured <see cref="HttpClient"/> (base address + auth).</param>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the store.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="options">Provider options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <exception cref="ArgumentException"></exception>
    /// <remarks>
    /// The base address of the required mem0 service, and any authentication headers, should be set on the <paramref name="httpClient"/>
    /// already, when passed as a parameter here. E.g.:
    /// <code>
    /// using var httpClient = new HttpClient();
    /// httpClient.BaseAddress = new Uri("https://api.mem0.ai");
    /// httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Token", "&lt;Your APIKey&gt;");
    /// new Mem0AIContextProvider(httpClient, state);
    /// </code>
    /// </remarks>
    public Mem0Provider(HttpClient httpClient, JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, Mem0ProviderOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        if (string.IsNullOrWhiteSpace(httpClient.BaseAddress?.AbsoluteUri))
        {
            throw new ArgumentException("The HttpClient BaseAddress must be set for Mem0 operations.", nameof(httpClient));
        }

        this._logger = loggerFactory?.CreateLogger<Mem0Provider>();
        this._client = new Mem0Client(httpClient);

        this._contextPrompt = options?.ContextPrompt ?? DefaultContextPrompt;
        this._enableSensitiveTelemetryData = options?.EnableSensitiveTelemetryData ?? false;

        var jso = jsonSerializerOptions ?? Mem0JsonUtilities.DefaultOptions;
        var state = serializedState.Deserialize(jso.GetTypeInfo(typeof(Mem0State))) as Mem0State;

        if (state == null || state.StorageScope == null || state.SearchScope == null)
        {
            throw new InvalidOperationException("The Mem0Provider state did not contain the required scope properties.");
        }

        this._storageScope = state.StorageScope;
        this._searchScope = state.SearchScope;
    }

    /// <inheritdoc />
    public override async ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);

        string queryText = string.Join(
            Environment.NewLine,
            context.RequestMessages.Where(m => !string.IsNullOrWhiteSpace(m.Text)).Select(m => m.Text));

        try
        {
            var memories = (await this._client.SearchAsync(
                this._searchScope.ApplicationId,
                this._searchScope.AgentId,
                this._searchScope.ThreadId,
                this._searchScope.UserId,
                queryText,
                cancellationToken).ConfigureAwait(false)).ToList();

            var outputMessageText = memories.Count == 0
                ? null
                : $"{this._contextPrompt}\n{string.Join(Environment.NewLine, memories)}";

            if (this._logger is not null)
            {
                this._logger.LogInformation(
                    "Mem0AIContextProvider: Retrieved {Count} memories. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', ThreadId: '{ThreadId}', UserId: '{UserId}'.",
                    memories.Count,
                    this._searchScope.ApplicationId,
                    this._searchScope.AgentId,
                    this._searchScope.ThreadId,
                    this.SanitizeLogData(this._searchScope.UserId));
                if (outputMessageText is not null)
                {
                    this._logger.LogTrace(
                        "Mem0AIContextProvider: Search Results\nInput:{Input}\nOutput:{MessageText}\nApplicationId: '{ApplicationId}', AgentId: '{AgentId}', ThreadId: '{ThreadId}', UserId: '{UserId}'.",
                        this.SanitizeLogData(queryText),
                        this.SanitizeLogData(outputMessageText),
                        this._searchScope.ApplicationId,
                        this._searchScope.AgentId,
                        this._searchScope.ThreadId,
                        this.SanitizeLogData(this._searchScope.UserId));
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
            this._logger?.LogError(
                ex,
                "Mem0AIContextProvider: Failed to search Mem0 for memories due to error. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', ThreadId: '{ThreadId}', UserId: '{UserId}'.",
                this._searchScope.ApplicationId,
                this._searchScope.AgentId,
                this._searchScope.ThreadId,
                this.SanitizeLogData(this._searchScope.UserId));
            return new AIContext();
        }
    }

    /// <inheritdoc />
    public override async ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            return; // Do not update memory on failed invocations.
        }

        try
        {
            // Persist request and response messages after invocation.
            await this.PersistMessagesAsync(context.RequestMessages.Concat(context.ResponseMessages ?? []), cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            this._logger?.LogError(
                ex,
                "Mem0AIContextProvider: Failed to send messages to Mem0 due to error. ApplicationId: '{ApplicationId}', AgentId: '{AgentId}', ThreadId: '{ThreadId}', UserId: '{UserId}'.",
                this._storageScope.ApplicationId,
                this._storageScope.AgentId,
                this._storageScope.ThreadId,
                this.SanitizeLogData(this._storageScope.UserId));
        }
    }

    /// <summary>
    /// Clears stored memories for the configured scopes.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    public Task ClearStoredMemoriesAsync(CancellationToken cancellationToken = default) =>
        this._client.ClearMemoryAsync(
            this._storageScope.ApplicationId,
            this._storageScope.AgentId,
            this._storageScope.ThreadId,
            this._storageScope.UserId,
            cancellationToken);

    /// <inheritdoc />
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var state = new Mem0State(this._storageScope, this._searchScope);

        var jso = jsonSerializerOptions ?? Mem0JsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(state, jso.GetTypeInfo(typeof(Mem0State)));
    }

    private async Task PersistMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
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
                this._storageScope.ApplicationId,
                this._storageScope.AgentId,
                this._storageScope.ThreadId,
                this._storageScope.UserId,
                message.Text,
                message.Role.Value,
                cancellationToken).ConfigureAwait(false);
        }
    }

    internal sealed class Mem0State
    {
        [JsonConstructor]
        public Mem0State(Mem0ProviderScope storageScope, Mem0ProviderScope searchScope)
        {
            this.StorageScope = storageScope;
            this.SearchScope = searchScope;
        }

        public Mem0ProviderScope StorageScope { get; set; }
        public Mem0ProviderScope SearchScope { get; set; }
    }

    private string? SanitizeLogData(string? data) => this._enableSensitiveTelemetryData ? data : "<redacted>";
}
