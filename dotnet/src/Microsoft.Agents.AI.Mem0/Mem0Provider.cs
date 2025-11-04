// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
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

    private readonly Mem0Client _client;
    private readonly ILogger<Mem0Provider>? _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="Mem0Provider"/> class.
    /// </summary>
    /// <param name="httpClient">Configured <see cref="HttpClient"/> (base address + auth).</param>
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
    public Mem0Provider(HttpClient httpClient, Mem0ProviderOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        if (string.IsNullOrWhiteSpace(httpClient.BaseAddress?.AbsoluteUri))
        {
            throw new ArgumentException("The HttpClient BaseAddress must be set for Mem0 operations.", nameof(httpClient));
        }

        this.ApplicationId = options?.ApplicationId;
        this.AgentId = options?.AgentId;
        this.ThreadId = options?.ThreadId;
        this.UserId = options?.UserId;
        this._contextPrompt = options?.ContextPrompt ?? DefaultContextPrompt;

        this._logger = loggerFactory?.CreateLogger<Mem0Provider>();
        this._client = new Mem0Client(httpClient);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="Mem0Provider"/> class, with existing state from a serialized JSON element.
    /// </summary>
    /// <param name="httpClient">Configured <see cref="HttpClient"/> (base address + auth).</param>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the store.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
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
    public Mem0Provider(HttpClient httpClient, JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, ILoggerFactory? loggerFactory = null)
    {
        if (string.IsNullOrWhiteSpace(httpClient.BaseAddress?.AbsoluteUri))
        {
            throw new ArgumentException("The HttpClient BaseAddress must be set for Mem0 operations.", nameof(httpClient));
        }

        var jso = jsonSerializerOptions ?? Mem0JsonUtilities.DefaultOptions;
        var state = serializedState.Deserialize(jso.GetTypeInfo(typeof(Mem0State))) as Mem0State;

        this.ApplicationId = state?.ApplicationId;
        this.AgentId = state?.AgentId;
        this.ThreadId = state?.ThreadId;
        this.UserId = state?.UserId;
        this._contextPrompt = state?.ContextPrompt ?? DefaultContextPrompt;

        this._logger = loggerFactory?.CreateLogger<Mem0Provider>();
        this._client = new Mem0Client(httpClient);
    }

    /// <summary>
    /// Gets or sets an optional ID for the application to scope memories to.
    /// </summary>
    public string? ApplicationId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the agent to scope memories to.
    /// </summary>
    public string? AgentId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the thread to scope memories to.
    /// </summary>
    public string? ThreadId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the user to scope memories to.
    /// </summary>
    public string? UserId { get; set; }

    /// <inheritdoc />
    public override async ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);

        string queryText = string.Join(
            Environment.NewLine,
            context.RequestMessages.Where(m => !string.IsNullOrWhiteSpace(m.Text)).Select(m => m.Text));

        var memories = (await this._client.SearchAsync(
            this.ApplicationId,
            this.AgentId,
            this.ThreadId,
            this.UserId,
            queryText,
            cancellationToken).ConfigureAwait(false)).ToList();

        var contextInstructions = memories.Count == 0
            ? null
            : $"{this._contextPrompt}\n{string.Join(Environment.NewLine, memories)}";

        if (this._logger is not null)
        {
            this._logger.LogInformation("Mem0AIContextProvider retrieved {Count} memories.", memories.Count);
            if (contextInstructions is not null)
            {
                this._logger.LogTrace("Mem0AIContextProvider instructions: {Instructions}", contextInstructions);
            }
        }

        return new AIContext
        {
            Messages = [new ChatMessage(ChatRole.User, contextInstructions)]
        };
    }

    /// <inheritdoc />
    public override async ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            return; // Do not update memory on failed invocations.
        }

        // Persist request and response messages after invocation.
        await this.PersistMessagesAsync(context.RequestMessages, cancellationToken).ConfigureAwait(false);

        if (context.ResponseMessages is not null)
        {
            await this.PersistMessagesAsync(context.ResponseMessages, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Clears stored memories for the configured scopes.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    public Task ClearStoredMemoriesAsync(CancellationToken cancellationToken = default) =>
        this._client.ClearMemoryAsync(
            this.ApplicationId,
            this.AgentId,
            this.ThreadId,
            this.UserId,
            cancellationToken);

    /// <inheritdoc />
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var state = new Mem0State
        {
            ApplicationId = this.ApplicationId,
            AgentId = this.AgentId,
            ThreadId = this.ThreadId,
            UserId = this.UserId,
            ContextPrompt = this._contextPrompt == DefaultContextPrompt ? null : this._contextPrompt
        };

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
                this.ApplicationId,
                this.AgentId,
                this.ThreadId,
                this.UserId,
                message.Text,
                message.Role.Value,
                cancellationToken).ConfigureAwait(false);
        }
    }

    internal sealed class Mem0State
    {
        public string? ApplicationId { get; set; }
        public string? AgentId { get; set; }
        public string? UserId { get; set; }
        public string? ThreadId { get; set; }
        public string? ContextPrompt { get; set; }
    }
}
