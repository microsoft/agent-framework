// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Microsoft.Agents.AI.FoundryMemory.Core.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

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
public sealed class FoundryMemoryProvider : AIContextProvider
{
    private const string DefaultContextPrompt = "## Memories\nConsider the following memories when answering user questions:";

    private readonly string _contextPrompt;
    private readonly string _memoryStoreName;
    private readonly int _maxMemories;
    private readonly int _updateDelay;
    private readonly bool _enableSensitiveTelemetryData;

    private readonly AIProjectClient _client;
    private readonly ILogger<FoundryMemoryProvider>? _logger;

    private readonly FoundryMemoryProviderScope _scope;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryMemoryProvider"/> class.
    /// </summary>
    /// <param name="client">The Azure AI Project client configured for your Foundry project.</param>
    /// <param name="scope">The scope configuration for memory storage and retrieval.</param>
    /// <param name="options">Provider options including memory store name.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public FoundryMemoryProvider(
        AIProjectClient client,
        FoundryMemoryProviderScope scope,
        FoundryMemoryProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(scope);

        if (string.IsNullOrWhiteSpace(scope.Scope))
        {
            throw new ArgumentException("The Scope property must be provided.", nameof(scope));
        }

        FoundryMemoryProviderOptions effectiveOptions = options ?? new FoundryMemoryProviderOptions();

        if (string.IsNullOrWhiteSpace(effectiveOptions.MemoryStoreName))
        {
            throw new ArgumentException("The MemoryStoreName option must be provided.", nameof(options));
        }

        this._logger = loggerFactory?.CreateLogger<FoundryMemoryProvider>();
        this._client = client;

        this._contextPrompt = effectiveOptions.ContextPrompt ?? DefaultContextPrompt;
        this._memoryStoreName = effectiveOptions.MemoryStoreName;
        this._maxMemories = effectiveOptions.MaxMemories;
        this._updateDelay = effectiveOptions.UpdateDelay;
        this._enableSensitiveTelemetryData = effectiveOptions.EnableSensitiveTelemetryData;
        this._scope = new FoundryMemoryProviderScope(scope);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryMemoryProvider"/> class, with existing state from a serialized JSON element.
    /// </summary>
    /// <param name="client">The Azure AI Project client configured for your Foundry project.</param>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the provider.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="options">Provider options including memory store name.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public FoundryMemoryProvider(
        AIProjectClient client,
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        FoundryMemoryProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);

        FoundryMemoryProviderOptions effectiveOptions = options ?? new FoundryMemoryProviderOptions();

        if (string.IsNullOrWhiteSpace(effectiveOptions.MemoryStoreName))
        {
            throw new ArgumentException("The MemoryStoreName option must be provided.", nameof(options));
        }

        this._logger = loggerFactory?.CreateLogger<FoundryMemoryProvider>();
        this._client = client;

        this._contextPrompt = effectiveOptions.ContextPrompt ?? DefaultContextPrompt;
        this._memoryStoreName = effectiveOptions.MemoryStoreName;
        this._maxMemories = effectiveOptions.MaxMemories;
        this._updateDelay = effectiveOptions.UpdateDelay;
        this._enableSensitiveTelemetryData = effectiveOptions.EnableSensitiveTelemetryData;

        JsonSerializerOptions jso = jsonSerializerOptions ?? FoundryMemoryJsonUtilities.DefaultOptions;
        FoundryMemoryState? state = serializedState.Deserialize(jso.GetTypeInfo(typeof(FoundryMemoryState))) as FoundryMemoryState;

        if (state?.Scope == null || string.IsNullOrWhiteSpace(state.Scope.Scope))
        {
            throw new InvalidOperationException("The FoundryMemoryProvider state did not contain the required scope property.");
        }

        this._scope = state.Scope;
    }

    /// <inheritdoc />
    public override async ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);

#pragma warning disable CA1308 // Lowercase required by service
        MemoryInputMessage[] messageItems = context.RequestMessages
            .Where(m => !string.IsNullOrWhiteSpace(m.Text))
            .Select(m => new MemoryInputMessage
            {
                Role = m.Role.Value.ToLowerInvariant(),
                Content = m.Text!
            })
            .ToArray();
#pragma warning restore CA1308

        if (messageItems.Length == 0)
        {
            return new AIContext();
        }

        try
        {
            SearchMemoriesResponse? response = await this._client.SearchMemoriesAsync(
                this._memoryStoreName,
                this._scope.Scope!,
                messageItems,
                this._maxMemories,
                cancellationToken).ConfigureAwait(false);

            var memories = response?.Memories?
                .Select(m => m.MemoryItem?.Content ?? string.Empty)
                .Where(c => !string.IsNullOrWhiteSpace(c))
                .ToList() ?? [];

            string? outputMessageText = memories.Count == 0
                ? null
                : $"{this._contextPrompt}\n{string.Join(Environment.NewLine, memories)}";

            if (this._logger?.IsEnabled(LogLevel.Information) is true)
            {
                this._logger.LogInformation(
                    "FoundryMemoryProvider: Retrieved {Count} memories. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                    memories.Count,
                    this._memoryStoreName,
                    this.SanitizeLogData(this._scope.Scope));

                if (outputMessageText is not null && this._logger.IsEnabled(LogLevel.Trace))
                {
                    this._logger.LogTrace(
                        "FoundryMemoryProvider: Search Results\nOutput:{MessageText}\nMemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                        this.SanitizeLogData(outputMessageText),
                        this._memoryStoreName,
                        this.SanitizeLogData(this._scope.Scope));
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
                    this.SanitizeLogData(this._scope.Scope));
            }

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
#pragma warning disable CA1308 // Lowercase required by service
            MemoryInputMessage[] messageItems = context.RequestMessages
                .Concat(context.ResponseMessages ?? [])
                .Where(m => IsAllowedRole(m.Role) && !string.IsNullOrWhiteSpace(m.Text))
                .Select(m => new MemoryInputMessage
                {
                    Role = m.Role.Value.ToLowerInvariant(),
                    Content = m.Text!
                })
                .ToArray();
#pragma warning restore CA1308

            if (messageItems.Length == 0)
            {
                return;
            }

            UpdateMemoriesResponse? response = await this._client.UpdateMemoriesAsync(
                this._memoryStoreName,
                this._scope.Scope!,
                messageItems,
                this._updateDelay,
                cancellationToken).ConfigureAwait(false);

            if (this._logger?.IsEnabled(LogLevel.Information) is true)
            {
                this._logger.LogInformation(
                    "FoundryMemoryProvider: Sent {Count} messages to update memories. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}', UpdateId: '{UpdateId}'.",
                    messageItems.Length,
                    this._memoryStoreName,
                    this.SanitizeLogData(this._scope.Scope),
                    response?.UpdateId);
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
                    this.SanitizeLogData(this._scope.Scope));
            }
        }
    }

    /// <summary>
    /// Ensures all stored memories for the configured scope are deleted.
    /// This method handles cases where the scope doesn't exist (no memories stored yet).
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    public async Task EnsureStoredMemoriesDeletedAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            await this._client.DeleteScopeAsync(this._memoryStoreName, this._scope.Scope!, cancellationToken).ConfigureAwait(false);
        }
        catch (ClientResultException ex) when (ex.Status == 404)
        {
            // Scope doesn't exist (no memories stored yet), nothing to delete
            if (this._logger?.IsEnabled(LogLevel.Debug) is true)
            {
                this._logger.LogDebug(
                    "FoundryMemoryProvider: No memories to delete for scope. MemoryStore: '{MemoryStoreName}', Scope: '{Scope}'.",
                    this._memoryStoreName,
                    this.SanitizeLogData(this._scope.Scope));
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

    /// <inheritdoc />
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        FoundryMemoryState state = new(this._scope);

        JsonSerializerOptions jso = jsonSerializerOptions ?? FoundryMemoryJsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(state, jso.GetTypeInfo(typeof(FoundryMemoryState)));
    }

    private static bool IsAllowedRole(ChatRole role) =>
        role == ChatRole.User || role == ChatRole.Assistant || role == ChatRole.System;

    private string? SanitizeLogData(string? data) => this._enableSensitiveTelemetryData ? data : "<redacted>";

    internal sealed class FoundryMemoryState
    {
        [JsonConstructor]
        public FoundryMemoryState(FoundryMemoryProviderScope scope)
        {
            this.Scope = scope;
        }

        public FoundryMemoryProviderScope Scope { get; set; }
    }
}
