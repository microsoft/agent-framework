// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
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
    /// Initializes a new instance of the <see cref="GithubCopilotAgent"/> class.
    /// </summary>
    /// <param name="copilotClient">The Copilot client to use for interacting with GitHub Copilot.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="tools">The tools to make available to the agent.</param>
    /// <param name="instructions">Optional instructions to append as a system message.</param>
    public GithubCopilotAgent(
        CopilotClient copilotClient,
        bool ownsClient = false,
        string? id = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        string? instructions = null)
        : this(
            copilotClient,
            GetSessionConfig(tools, instructions),
            ownsClient,
            id,
            name ?? "GitHub Copilot Agent",
            description ?? "An AI agent powered by GitHub Copilot")
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

        // Create or resume a session
        CopilotSession session;
        if (typedThread.SessionId is not null)
        {
            session = await this._copilotClient.ResumeSessionAsync(
                typedThread.SessionId,
                this.CreateResumeConfig(),
                cancellationToken).ConfigureAwait(false);
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

            List<string> tempFiles = [];
            try
            {
                // Build prompt from text content
                string prompt = string.Join("\n", messages.Select(m => m.Text));

                // Handle DataContent as attachments
                List<UserMessageDataAttachmentsItem>? attachments = await ProcessDataContentAttachmentsAsync(
                    messages,
                    tempFiles,
                    cancellationToken).ConfigureAwait(false);

                // Send the message with attachments
                MessageOptions messageOptions = new() { Prompt = prompt };
                if (attachments is not null)
                {
                    messageOptions.Attachments = [.. attachments];
                }

                await session.SendAsync(messageOptions, cancellationToken).ConfigureAwait(false);

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
                CleanupTempFiles(tempFiles);
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
                OnPermissionRequest = this._sessionConfig.OnPermissionRequest,
                McpServers = this._sessionConfig.McpServers,
                CustomAgents = this._sessionConfig.CustomAgents,
                SkillDirectories = this._sessionConfig.SkillDirectories,
                DisabledSkills = this._sessionConfig.DisabledSkills,
                Streaming = true
            }
            : new SessionConfig { Streaming = true };

        CopilotSession session;
        if (typedThread.SessionId is not null)
        {
            session = await this._copilotClient.ResumeSessionAsync(
                typedThread.SessionId,
                this.CreateResumeConfig(streaming: true),
                cancellationToken).ConfigureAwait(false);
        }
        else
        {
            session = await this._copilotClient.CreateSessionAsync(sessionConfig, cancellationToken).ConfigureAwait(false);
            typedThread.SessionId = session.SessionId;
        }

        try
        {
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

            List<string> tempFiles = [];
            try
            {
                // Build prompt from text content
                string prompt = string.Join("\n", messages.Select(m => m.Text));

                // Handle DataContent as attachments
                List<UserMessageDataAttachmentsItem>? attachments = await ProcessDataContentAttachmentsAsync(
                    messages,
                    tempFiles,
                    cancellationToken).ConfigureAwait(false);

                // Send the message with attachments
                MessageOptions messageOptions = new() { Prompt = prompt };
                if (attachments is not null)
                {
                    messageOptions.Attachments = [.. attachments];
                }

                await session.SendAsync(messageOptions, cancellationToken).ConfigureAwait(false);

                // Yield updates as they arrive
                await foreach (AgentResponseUpdate update in channel.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
                {
                    yield return update;
                }
            }
            finally
            {
                subscription.Dispose();
                CleanupTempFiles(tempFiles);
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

    private ResumeSessionConfig CreateResumeConfig(bool streaming = false)
    {
        return new ResumeSessionConfig
        {
            Tools = this._sessionConfig?.Tools,
            Provider = this._sessionConfig?.Provider,
            OnPermissionRequest = this._sessionConfig?.OnPermissionRequest,
            McpServers = this._sessionConfig?.McpServers,
            CustomAgents = this._sessionConfig?.CustomAgents,
            SkillDirectories = this._sessionConfig?.SkillDirectories,
            DisabledSkills = this._sessionConfig?.DisabledSkills,
            Streaming = streaming,
        };
    }

    private ChatMessage ConvertToChatMessage(AssistantMessageEvent assistantMessage)
    {
        return new ChatMessage(ChatRole.Assistant, assistantMessage.Data?.Content ?? string.Empty)
        {
            MessageId = assistantMessage.Data?.MessageId,
            CreatedAt = DateTimeOffset.UtcNow
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantMessageDeltaEvent deltaEvent)
    {
        return new AgentResponseUpdate(ChatRole.Assistant, [new TextContent(deltaEvent.Data?.DeltaContent ?? string.Empty)])
        {
            AgentId = this.Id,
            MessageId = deltaEvent.Data?.MessageId,
            CreatedAt = DateTimeOffset.UtcNow
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantMessageEvent assistantMessage)
    {
        return new AgentResponseUpdate(ChatRole.Assistant, [new TextContent(assistantMessage.Data?.Content ?? string.Empty)])
        {
            AgentId = this.Id,
            ResponseId = assistantMessage.Data?.MessageId,
            MessageId = assistantMessage.Data?.MessageId,
            CreatedAt = DateTimeOffset.UtcNow
        };
    }

    private static SessionConfig? GetSessionConfig(IList<AITool>? tools, string? instructions)
    {
        List<AIFunction>? mappedTools = tools is { Count: > 0 } ? tools.OfType<AIFunction>().ToList() : null;
        SystemMessageConfig? systemMessage = instructions is not null ? new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = instructions } : null;

        if (mappedTools is null && systemMessage is null)
        {
            return null;
        }

        return new SessionConfig { Tools = mappedTools, SystemMessage = systemMessage };
    }

    private static readonly Dictionary<string, string> s_mediaTypeExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ["image/png"] = ".png",
        ["image/jpeg"] = ".jpg",
        ["image/jpg"] = ".jpg",
        ["image/gif"] = ".gif",
        ["image/webp"] = ".webp",
        ["image/svg+xml"] = ".svg",
        ["text/plain"] = ".txt",
        ["text/html"] = ".html",
        ["text/markdown"] = ".md",
        ["application/json"] = ".json",
        ["application/xml"] = ".xml",
        ["application/pdf"] = ".pdf"
    };

    private static string GetExtensionForMediaType(string? mediaType)
    {
        return mediaType is not null && s_mediaTypeExtensions.TryGetValue(mediaType, out string? extension) ? extension : ".dat";
    }

    private static async Task<List<UserMessageDataAttachmentsItem>?> ProcessDataContentAttachmentsAsync(
        IEnumerable<ChatMessage> messages,
        List<string> tempFiles,
        CancellationToken cancellationToken)
    {
        List<UserMessageDataAttachmentsItem>? attachments = null;
        foreach (ChatMessage message in messages)
        {
            foreach (AIContent content in message.Contents)
            {
                if (content is DataContent dataContent)
                {
                    // Write DataContent to a temp file
                    string tempFilePath = Path.Combine(Path.GetTempPath(), $"agentframework_copilot_data_{Guid.NewGuid()}{GetExtensionForMediaType(dataContent.MediaType)}");
                    await File.WriteAllBytesAsync(tempFilePath, dataContent.Data.ToArray(), cancellationToken).ConfigureAwait(false);
                    tempFiles.Add(tempFilePath);

                    // Create attachment
                    attachments ??= [];
                    attachments.Add(new UserMessageDataAttachmentsItem
                    {
                        Type = UserMessageDataAttachmentsItemType.File,
                        Path = tempFilePath,
                        DisplayName = Path.GetFileName(tempFilePath)
                    });
                }
            }
        }

        return attachments;
    }

    private static void CleanupTempFiles(List<string> tempFiles)
    {
        foreach (string tempFile in tempFiles)
        {
            try
            {
                if (File.Exists(tempFile))
                {
                    File.Delete(tempFile);
                }
            }
            catch
            {
                // Best effort cleanup
            }
        }
    }
}
