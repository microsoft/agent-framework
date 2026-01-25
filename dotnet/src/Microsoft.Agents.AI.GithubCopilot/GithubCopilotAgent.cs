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
    private readonly bool _ownsClient;

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgent"/> class.
    /// </summary>
    /// <param name="copilotClient">The Copilot client to use for interacting with GitHub Copilot.</param>
    /// <param name="sessionConfig">Optional session configuration for the agent.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    public GithubCopilotAgent(
        CopilotClient copilotClient,
        SessionConfig? sessionConfig = null,
        bool ownsClient = false,
        string? id = null,
        string? name = null,
        string? description = null)
    {
        _ = Throw.IfNull(copilotClient);

        this._copilotClient = copilotClient;
        this._sessionConfig = sessionConfig;
        this._ownsClient = ownsClient;
        this._id = id;
        this._name = name;
        this._description = description;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgent"/> class with tools.
    /// </summary>
    /// <param name="copilotClient">The Copilot client to use for interacting with GitHub Copilot.</param>
    /// <param name="tools">The tools to make available to the agent.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    public GithubCopilotAgent(
        CopilotClient copilotClient,
        IList<AITool>? tools,
        bool ownsClient = false,
        string? id = null,
        string? name = null,
        string? description = null)
        : this(
            copilotClient,
            tools is { Count: > 0 } ? new SessionConfig { Tools = tools.OfType<AIFunction>().ToList() } : null,
            ownsClient,
            id,
            name,
            description)
    {
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

        // Get or create session
        CopilotSession session = await this.GetOrCreateSessionAsync(typedThread, cancellationToken).ConfigureAwait(false);

        // Prepare to collect response
        List<ChatMessage> responseMessages = [];
        TaskCompletionSource<bool> completionSource = new();

        // Subscribe to session events
        IDisposable subscription = session.On(evt =>
        {
            switch (evt)
            {
                case AssistantMessageEvent assistantMessage:
                    responseMessages.Add(this.ConvertToChatMessage(assistantMessage));
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

        // Get or create session with streaming enabled
        CopilotSession session = await this.GetOrCreateSessionAsync(typedThread, cancellationToken, streaming: true).ConfigureAwait(false);

        System.Threading.Channels.Channel<AgentResponseUpdate> channel = System.Threading.Channels.Channel.CreateUnbounded<AgentResponseUpdate>();

        // Subscribe to session events
        IDisposable subscription = session.On(evt =>
        {
            switch (evt)
            {
                case AssistantMessageDeltaEvent deltaEvent:
                    channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(deltaEvent));
                    break;

                case AssistantMessageEvent assistantMessage:
                    channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(assistantMessage));
                    break;

                case SessionIdleEvent:
                    channel.Writer.TryComplete();
                    break;

                    case SessionErrorEvent errorEvent:
                        Exception exception = new InvalidOperationException(
                            $"Session error: {errorEvent.Data?.Message ?? "Unknown error"}");
                        channel.Writer.TryComplete(exception);
                        break;
                }
            });

            try
            {
                // Send the message
                string prompt = string.Join("\n", messages.Select(m => m.Text));
                await session.SendAsync(new MessageOptions { Prompt = prompt }, cancellationToken).ConfigureAwait(false);

                // Yield updates as they arrive
                await foreach (AgentResponseUpdate update in channel.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
                {
                    yield return update;
                }
            }
            finally
            {
                subscription.Dispose();
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

    private async Task<CopilotSession> GetOrCreateSessionAsync(
        GithubCopilotAgentThread thread,
        CancellationToken cancellationToken,
        bool streaming = false)
    {
        // If thread already has an active session, reuse it
        if (thread.Session is not null)
        {
            return thread.Session;
        }

        // Create or resume session
        CopilotSession session;
        if (thread.SessionId is not null)
        {
            // Resume existing session
            ResumeSessionConfig resumeConfig = new() { Streaming = streaming };
            session = await this._copilotClient.ResumeSessionAsync(
                thread.SessionId,
                resumeConfig,
                cancellationToken).ConfigureAwait(false);
        }
        else
        {
            // Create new session
            SessionConfig sessionConfig = this._sessionConfig != null
                ? new SessionConfig
                {
                    Model = this._sessionConfig.Model,
                    Tools = this._sessionConfig.Tools,
                    SystemMessage = this._sessionConfig.SystemMessage,
                    AvailableTools = this._sessionConfig.AvailableTools,
                    ExcludedTools = this._sessionConfig.ExcludedTools,
                    Provider = this._sessionConfig.Provider,
                    Streaming = streaming
                }
                : new SessionConfig { Streaming = streaming };

            session = await this._copilotClient.CreateSessionAsync(sessionConfig, cancellationToken).ConfigureAwait(false);
            thread.SessionId = session.SessionId;
        }

        // Store session in thread
        thread.Session = session;
        return session;
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
