// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.GitHub.Copilot;

/// <summary>
/// Represents an <see cref="AIAgent"/> that uses the GitHub Copilot SDK to provide agentic capabilities.
/// </summary>
public sealed class GitHubCopilotAgent : AIAgent, IAsyncDisposable
{
    private const string DefaultName = "GitHub Copilot Agent";
    private const string DefaultDescription = "An AI agent powered by GitHub Copilot";

    private readonly CopilotClient _copilotClient;
    private readonly string? _id;
    private readonly string _name;
    private readonly string _description;
    private readonly SessionConfig? _sessionConfig;
    private readonly bool _ownsClient;

    /// <summary>
    /// Initializes a new instance of the <see cref="GitHubCopilotAgent"/> class.
    /// </summary>
    /// <param name="copilotClient">The Copilot client to use for interacting with GitHub Copilot.</param>
    /// <param name="sessionConfig">Optional session configuration for the agent.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    public GitHubCopilotAgent(
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
        this._name = name ?? DefaultName;
        this._description = description ?? DefaultDescription;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="GitHubCopilotAgent"/> class.
    /// </summary>
    /// <param name="copilotClient">The Copilot client to use for interacting with GitHub Copilot.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="tools">The tools to make available to the agent.</param>
    /// <param name="instructions">Optional instructions to append as a system message.</param>
    public GitHubCopilotAgent(
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
            name,
            description)
    {
    }

    /// <inheritdoc/>
    protected sealed override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new GitHubCopilotAgentSession());

    /// <summary>
    /// Get a new <see cref="AgentSession"/> instance using an existing session id, to continue that conversation.
    /// </summary>
    /// <param name="sessionId">The session id to continue.</param>
    /// <returns>A new <see cref="AgentSession"/> instance.</returns>
    public ValueTask<AgentSession> CreateSessionAsync(string sessionId)
        => new(new GitHubCopilotAgentSession() { SessionId = sessionId });

    /// <inheritdoc/>
    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(session);

        if (session is not GitHubCopilotAgentSession typedSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(GitHubCopilotAgentSession)}' can be serialized by this agent.");
        }

        return new(typedSession.Serialize(jsonSerializerOptions));
    }

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(GitHubCopilotAgentSession.Deserialize(serializedState, jsonSerializerOptions));

    /// <inheritdoc/>
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this.RunCoreStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // Ensure we have a valid session
        session ??= await this.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        if (session is not GitHubCopilotAgentSession typedSession)
        {
            throw new InvalidOperationException(
                $"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(GitHubCopilotAgentSession)}' can be used by this agent.");
        }

        // Ensure the client is started
        await this.EnsureClientStartedAsync(cancellationToken).ConfigureAwait(false);

        // Create or resume a session with streaming enabled
        SessionConfig sessionConfig = this._sessionConfig != null
            ? CopySessionConfig(this._sessionConfig)
            : new SessionConfig { Streaming = true };

        CopilotSession copilotSession;
        if (typedSession.SessionId is not null)
        {
            copilotSession = await this._copilotClient.ResumeSessionAsync(
                typedSession.SessionId,
                this.CreateResumeConfig(),
                cancellationToken).ConfigureAwait(false);
        }
        else
        {
            copilotSession = await this._copilotClient.CreateSessionAsync(sessionConfig, cancellationToken).ConfigureAwait(false);
            typedSession.SessionId = copilotSession.SessionId;
        }

        try
        {
            Channel<AgentResponseUpdate> channel = Channel.CreateUnbounded<AgentResponseUpdate>();

            // Subscribe to session events
            using IDisposable subscription = copilotSession.On(evt =>
            {
                switch (evt)
                {
                    case AssistantMessageDeltaEvent deltaEvent:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(deltaEvent));
                        break;

                    case AssistantMessageEvent assistantMessage:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(assistantMessage));
                        break;

                    case AssistantUsageEvent usageEvent:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(usageEvent));
                        break;

                    case SessionIdleEvent idleEvent:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(idleEvent));
                        channel.Writer.TryComplete();
                        break;

                    case SessionErrorEvent errorEvent:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(errorEvent));
                        channel.Writer.TryComplete(new InvalidOperationException(
                            $"Session error: {errorEvent.Data?.Message ?? "Unknown error"}"));
                        break;

                    default:
                        // Handle all other event types by storing as RawRepresentation
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(evt));
                        break;
                }
            });

            string? tempDir = null;
            try
            {
                // Build prompt from text content
                string prompt = string.Join("\n", messages.Select(m => m.Text));

                // Handle DataContent as attachments
                (List<UserMessageDataAttachmentsItem>? attachments, tempDir) = await ProcessDataContentAttachmentsAsync(
                    messages,
                    cancellationToken).ConfigureAwait(false);

                // Send the message with attachments
                MessageOptions messageOptions = new() { Prompt = prompt };
                if (attachments is not null)
                {
                    messageOptions.Attachments = [.. attachments];
                }

                await copilotSession.SendAsync(messageOptions, cancellationToken).ConfigureAwait(false);
                // Yield updates as they arrive
                await foreach (AgentResponseUpdate update in channel.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
                {
                    yield return update;
                }
            }
            finally
            {
                CleanupTempDir(tempDir);
            }
        }
        finally
        {
            await copilotSession.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    protected override string? IdCore => this._id;

    /// <inheritdoc/>
    public override string Name => this._name;

    /// <inheritdoc/>
    public override string Description => this._description;

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

    private ResumeSessionConfig CreateResumeConfig()
    {
        return CopyResumeSessionConfig(this._sessionConfig);
    }

    /// <summary>
    /// Copies all supported properties from a source <see cref="SessionConfig"/> into a new instance
    /// with <see cref="SessionConfig.Streaming"/> set to <c>true</c>.
    /// </summary>
    internal static SessionConfig CopySessionConfig(SessionConfig source)
    {
        return new SessionConfig
        {
            Model = source.Model,
            ReasoningEffort = source.ReasoningEffort,
            Tools = source.Tools,
            SystemMessage = source.SystemMessage,
            AvailableTools = source.AvailableTools,
            ExcludedTools = source.ExcludedTools,
            Provider = source.Provider,
            OnPermissionRequest = source.OnPermissionRequest,
            OnUserInputRequest = source.OnUserInputRequest,
            Hooks = source.Hooks,
            WorkingDirectory = source.WorkingDirectory,
            ConfigDir = source.ConfigDir,
            McpServers = source.McpServers,
            CustomAgents = source.CustomAgents,
            SkillDirectories = source.SkillDirectories,
            DisabledSkills = source.DisabledSkills,
            InfiniteSessions = source.InfiniteSessions,
            Streaming = true
        };
    }

    /// <summary>
    /// Copies all supported properties from a source <see cref="SessionConfig"/> into a new
    /// <see cref="ResumeSessionConfig"/> with <see cref="ResumeSessionConfig.Streaming"/> set to <c>true</c>.
    /// </summary>
    internal static ResumeSessionConfig CopyResumeSessionConfig(SessionConfig? source)
    {
        return new ResumeSessionConfig
        {
            Model = source?.Model,
            ReasoningEffort = source?.ReasoningEffort,
            Tools = source?.Tools,
            SystemMessage = source?.SystemMessage,
            AvailableTools = source?.AvailableTools,
            ExcludedTools = source?.ExcludedTools,
            Provider = source?.Provider,
            OnPermissionRequest = source?.OnPermissionRequest,
            OnUserInputRequest = source?.OnUserInputRequest,
            Hooks = source?.Hooks,
            WorkingDirectory = source?.WorkingDirectory,
            ConfigDir = source?.ConfigDir,
            McpServers = source?.McpServers,
            CustomAgents = source?.CustomAgents,
            SkillDirectories = source?.SkillDirectories,
            DisabledSkills = source?.DisabledSkills,
            InfiniteSessions = source?.InfiniteSessions,
            Streaming = true
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantMessageDeltaEvent deltaEvent)
    {
        TextContent textContent = new(deltaEvent.Data?.DeltaContent ?? string.Empty)
        {
            RawRepresentation = deltaEvent
        };

        return new AgentResponseUpdate(ChatRole.Assistant, [textContent])
        {
            AgentId = this.Id,
            MessageId = deltaEvent.Data?.MessageId,
            CreatedAt = deltaEvent.Timestamp
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantMessageEvent assistantMessage)
    {
        TextContent textContent = new(assistantMessage.Data?.Content ?? string.Empty)
        {
            RawRepresentation = assistantMessage
        };

        return new AgentResponseUpdate(ChatRole.Assistant, [textContent])
        {
            AgentId = this.Id,
            ResponseId = assistantMessage.Data?.MessageId,
            MessageId = assistantMessage.Data?.MessageId,
            CreatedAt = assistantMessage.Timestamp
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantUsageEvent usageEvent)
    {
        UsageDetails usageDetails = new()
        {
            InputTokenCount = (int?)(usageEvent.Data?.InputTokens),
            OutputTokenCount = (int?)(usageEvent.Data?.OutputTokens),
            TotalTokenCount = (int?)((usageEvent.Data?.InputTokens ?? 0) + (usageEvent.Data?.OutputTokens ?? 0)),
            CachedInputTokenCount = (int?)(usageEvent.Data?.CacheReadTokens),
            AdditionalCounts = GetAdditionalCounts(usageEvent),
        };

        UsageContent usageContent = new(usageDetails)
        {
            RawRepresentation = usageEvent
        };

        return new AgentResponseUpdate(ChatRole.Assistant, [usageContent])
        {
            AgentId = this.Id,
            CreatedAt = usageEvent.Timestamp
        };
    }

    private static AdditionalPropertiesDictionary<long>? GetAdditionalCounts(AssistantUsageEvent usageEvent)
    {
        if (usageEvent.Data is null)
        {
            return null;
        }

        AdditionalPropertiesDictionary<long>? additionalCounts = null;

        if (usageEvent.Data.CacheWriteTokens is double cacheWriteTokens)
        {
            additionalCounts ??= [];
            additionalCounts[nameof(AssistantUsageData.CacheWriteTokens)] = (long)cacheWriteTokens;
        }

        if (usageEvent.Data.Cost is double cost)
        {
            additionalCounts ??= [];
            additionalCounts[nameof(AssistantUsageData.Cost)] = (long)cost;
        }

        if (usageEvent.Data.Duration is double duration)
        {
            additionalCounts ??= [];
            additionalCounts[nameof(AssistantUsageData.Duration)] = (long)duration;
        }

        return additionalCounts;
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(SessionEvent sessionEvent)
    {
        // Handle arbitrary events by storing as RawRepresentation
        AIContent content = new()
        {
            RawRepresentation = sessionEvent
        };

        return new AgentResponseUpdate(ChatRole.Assistant, [content])
        {
            AgentId = this.Id,
            CreatedAt = sessionEvent.Timestamp
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

    private static async Task<(List<UserMessageDataAttachmentsItem>? Attachments, string? TempDir)> ProcessDataContentAttachmentsAsync(
        IEnumerable<ChatMessage> messages,
        CancellationToken cancellationToken)
    {
        List<UserMessageDataAttachmentsItem>? attachments = null;
        string? tempDir = null;
        foreach (ChatMessage message in messages)
        {
            foreach (AIContent content in message.Contents)
            {
                if (content is DataContent dataContent)
                {
                    tempDir ??= Directory.CreateDirectory(
                        Path.Combine(Path.GetTempPath(), $"af_copilot_{Guid.NewGuid():N}")).FullName;

                    string tempFilePath = await dataContent.SaveToAsync(tempDir, cancellationToken).ConfigureAwait(false);

                    attachments ??= [];
                    attachments.Add(new UserMessageDataAttachmentsItemFile
                    {
                        Path = tempFilePath,
                        DisplayName = Path.GetFileName(tempFilePath)
                    });
                }
            }
        }

        return (attachments, tempDir);
    }

    private static void CleanupTempDir(string? tempDir)
    {
        if (tempDir is not null)
        {
            try
            {
                Directory.Delete(tempDir, recursive: true);
            }
            catch
            {
                // Best effort cleanup
            }
        }
    }
}
