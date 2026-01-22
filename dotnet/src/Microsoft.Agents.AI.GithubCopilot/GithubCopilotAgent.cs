// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.GithubCopilot;

/// <summary>
/// Represents an <see cref="AIAgent"/> that uses the GitHub Copilot SDK to provide agentic capabilities.
/// </summary>
public sealed class GithubCopilotAgent : AIAgent, IAsyncDisposable
{
    private readonly CopilotClient _copilotClient;
    private readonly string? _id;
    private readonly string? _name;
    private readonly string? _description;
    private readonly SessionConfig? _sessionConfig;
    private readonly ILogger _logger;
    private readonly bool _ownsClient;

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgent"/> class.
    /// </summary>
    /// <param name="copilotClient">The Copilot client to use for interacting with GitHub Copilot.</param>
    /// <param name="sessionConfig">Optional session configuration for the agent.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public GithubCopilotAgent(
        CopilotClient copilotClient,
        SessionConfig? sessionConfig = null,
        string? id = null,
        string? name = null,
        string? description = null,
        ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(copilotClient);

        this._copilotClient = copilotClient;
        this._sessionConfig = sessionConfig;
        this._id = id;
        this._name = name;
        this._description = description;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<GithubCopilotAgent>();
        this._ownsClient = false;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgent"/> class with custom options.
    /// </summary>
    /// <param name="copilotClientOptions">Options for creating the Copilot client.</param>
    /// <param name="sessionConfig">Optional session configuration for the agent.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public GithubCopilotAgent(
        CopilotClientOptions copilotClientOptions,
        SessionConfig? sessionConfig = null,
        string? id = null,
        string? name = null,
        string? description = null,
        ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(copilotClientOptions);

        this._copilotClient = new CopilotClient(copilotClientOptions);
        this._sessionConfig = sessionConfig;
        this._id = id;
        this._name = name;
        this._description = description;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<GithubCopilotAgent>();
        this._ownsClient = true;
    }

    /// <inheritdoc/>
    public sealed override ValueTask<AgentThread> GetNewThreadAsync(CancellationToken cancellationToken = default)
        => new(new GithubCopilotAgentThread());

    /// <summary>
    /// Get a new <see cref="AgentThread"/> instance using an existing session id, to continue that conversation.
    /// </summary>
    /// <param name="sessionId">The session id to continue.</param>
    /// <returns>A new <see cref="AgentThread"/> instance.</returns>
    public ValueTask<AgentThread> GetNewThreadAsync(string sessionId)
        => new(new GithubCopilotAgentThread() { SessionId = sessionId });

    /// <inheritdoc/>
    public override ValueTask<AgentThread> DeserializeThreadAsync(
        JsonElement serializedThread,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(new GithubCopilotAgentThread(serializedThread, jsonSerializerOptions));

    /// <inheritdoc/>
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // Ensure we have a valid thread
        thread ??= await this.GetNewThreadAsync(cancellationToken).ConfigureAwait(false);
        if (thread is not GithubCopilotAgentThread typedThread)
        {
            throw new InvalidOperationException(
                $"The provided thread type {thread.GetType()} is not compatible with the agent. Only GitHub Copilot agent created threads are supported.");
        }

        // Ensure the client is started
        await this.EnsureClientStartedAsync(cancellationToken).ConfigureAwait(false);

        // Create or resume a session
        CopilotSession session;
        if (typedThread.SessionId is not null)
        {
            session = await this._copilotClient.ResumeSessionAsync(typedThread.SessionId, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        else
        {
            session = await this._copilotClient.CreateSessionAsync(this._sessionConfig, cancellationToken).ConfigureAwait(false);
            typedThread.SessionId = session.SessionId;
        }

        try
        {
            // Prepare to collect response
            List<ChatMessage> responseMessages = [];
            TaskCompletionSource<bool> completionSource = new();

            // Subscribe to session events
            IDisposable subscription = session.On(evt =>
            {
                switch (evt)
                {
                    case AssistantMessageEvent assistantMessage:
                        responseMessages.Add(ConvertToChatMessage(assistantMessage));
                        break;

                    case SessionIdleEvent:
                        completionSource.TrySetResult(true);
                        break;

                    case SessionErrorEvent errorEvent:
                        completionSource.TrySetException(new InvalidOperationException(
                            $"Session error: {errorEvent.Data?.Message ?? "Unknown error"}"));
                        break;
                }
            });

            try
            {
                // Send the message
                string prompt = string.Join("\n", messages.Select(m => m.Text));
                await session.SendAsync(new MessageOptions { Prompt = prompt }, cancellationToken).ConfigureAwait(false);

                // Wait for completion
                await completionSource.Task.ConfigureAwait(false);

                return new AgentResponse(responseMessages)
                {
                    AgentId = this.Id,
                    ResponseId = responseMessages.LastOrDefault()?.MessageId,
                };
            }
            finally
            {
                subscription.Dispose();
            }
        }
        finally
        {
            await session.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // Ensure we have a valid thread
        thread ??= await this.GetNewThreadAsync(cancellationToken).ConfigureAwait(false);
        if (thread is not GithubCopilotAgentThread typedThread)
        {
            throw new InvalidOperationException(
                $"The provided thread type {thread.GetType()} is not compatible with the agent. Only GitHub Copilot agent created threads are supported.");
        }

        // Ensure the client is started
        await this.EnsureClientStartedAsync(cancellationToken).ConfigureAwait(false);

        // Create or resume a session with streaming enabled
        SessionConfig sessionConfig = this._sessionConfig != null
            ? new SessionConfig
            {
                Model = this._sessionConfig.Model,
                Tools = this._sessionConfig.Tools,
                SystemMessage = this._sessionConfig.SystemMessage,
                AvailableTools = this._sessionConfig.AvailableTools,
                ExcludedTools = this._sessionConfig.ExcludedTools,
                Provider = this._sessionConfig.Provider,
                Streaming = true
            }
            : new SessionConfig { Streaming = true };

        CopilotSession session;
        if (typedThread.SessionId is not null)
        {
            session = await this._copilotClient.ResumeSessionAsync(
                typedThread.SessionId,
                new ResumeSessionConfig { Streaming = true },
                cancellationToken).ConfigureAwait(false);
        }
        else
        {
            session = await this._copilotClient.CreateSessionAsync(sessionConfig, cancellationToken).ConfigureAwait(false);
            typedThread.SessionId = session.SessionId;
        }

        try
        {
            TaskCompletionSource<bool> completionSource = new();
            List<AgentResponseUpdate> updates = [];

            // Subscribe to session events
            IDisposable subscription = session.On(evt =>
            {
                switch (evt)
                {
                    case AssistantMessageDeltaEvent deltaEvent:
                        updates.Add(ConvertToAgentResponseUpdate(deltaEvent));
                        break;

                    case AssistantMessageEvent assistantMessage:
                        updates.Add(ConvertToAgentResponseUpdate(assistantMessage));
                        break;

                    case SessionIdleEvent:
                        completionSource.TrySetResult(true);
                        break;

                    case SessionErrorEvent errorEvent:
                        completionSource.TrySetException(new InvalidOperationException(
                            $"Session error: {errorEvent.Data?.Message ?? "Unknown error"}"));
                        break;
                }
            });

            try
            {
                // Send the message
                string prompt = string.Join("\n", messages.Select(m => m.Text));
                await session.SendAsync(new MessageOptions { Prompt = prompt }, cancellationToken).ConfigureAwait(false);

                // Wait for completion
                await completionSource.Task.ConfigureAwait(false);

                // Yield all collected updates
                foreach (AgentResponseUpdate update in updates)
                {
                    yield return update;
                }
            }
            finally
            {
                subscription.Dispose();
            }
        }
        finally
        {
            await session.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    protected override string? IdCore => this._id;

    /// <inheritdoc/>
    public override string? Name => this._name;

    /// <inheritdoc/>
    public override string? Description => this._description;

    /// <summary>
    /// Disposes the agent and releases resources.
    /// </summary>
    /// <returns>A value task representing the asynchronous dispose operation.</returns>
    public async ValueTask DisposeAsync()
    {
        if (this._ownsClient)
        {
            await this._copilotClient.DisposeAsync().ConfigureAwait(false);
        }
    }

    private async Task EnsureClientStartedAsync(CancellationToken cancellationToken)
    {
        if (this._copilotClient.State != ConnectionState.Connected)
        {
            await this._copilotClient.StartAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    private ChatMessage ConvertToChatMessage(AssistantMessageEvent assistantMessage)
    {
        return new ChatMessage(ChatRole.Assistant, assistantMessage.Data?.Content ?? string.Empty)
        {
            MessageId = assistantMessage.Data?.MessageId
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantMessageDeltaEvent deltaEvent)
    {
        return new AgentResponseUpdate(ChatRole.Assistant, [new TextContent(deltaEvent.Data?.DeltaContent ?? string.Empty)])
        {
            AgentId = this.Id,
            MessageId = deltaEvent.Data?.MessageId
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantMessageEvent assistantMessage)
    {
        return new AgentResponseUpdate(ChatRole.Assistant, [new TextContent(assistantMessage.Data?.Content ?? string.Empty)])
        {
            AgentId = this.Id,
            ResponseId = assistantMessage.Data?.MessageId,
            MessageId = assistantMessage.Data?.MessageId
        };
    }
}
