// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using GitHub.Copilot;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
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
    private readonly JsonSerializerOptions _jsonSerializerOptions;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="GitHubCopilotAgent"/> class.
    /// </summary>
    /// <param name="copilotClient">The Copilot client to use for interacting with GitHub Copilot.</param>
    /// <param name="sessionConfig">Optional session configuration for the agent.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options. Defaults to <see cref="GitHubCopilotJsonUtilities.DefaultOptions"/>.</param>
    /// <param name="loggerFactory">Optional logger factory used to create the agent's logger.</param>
    /// <remarks>
    /// When a tool wrapped in <see cref="ApprovalRequiredAIFunction"/> is registered and the supplied
    /// <paramref name="sessionConfig"/> does not already define a <c>Hooks.OnPreToolUse</c> handler, the agent installs a
    /// default <c>OnPreToolUse</c> hook that returns <c>"ask"</c> for those tools (routing the decision to
    /// <c>SessionConfig.OnPermissionRequest</c>) and defers all other tools. If the caller supplies their own
    /// <c>OnPreToolUse</c> hook, it takes precedence and the caller is fully responsible for approval handling; in that
    /// case a warning is logged for any approval-required tool that will not be automatically gated.
    /// </remarks>
    public GitHubCopilotAgent(
        CopilotClient copilotClient,
        SessionConfig? sessionConfig = null,
        bool ownsClient = false,
        string? id = null,
        string? name = null,
        string? description = null,
        JsonSerializerOptions? jsonSerializerOptions = null,
        ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(copilotClient);

        this._copilotClient = copilotClient;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<GitHubCopilotAgent>();
        this._sessionConfig = ConfigureApprovalHook(sessionConfig, this._logger);
        this._ownsClient = ownsClient;
        this._id = id;
        this._name = name ?? DefaultName;
        this._description = description ?? DefaultDescription;
        this._jsonSerializerOptions = jsonSerializerOptions ?? GitHubCopilotJsonUtilities.DefaultOptions;
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
    /// <param name="jsonSerializerOptions">Optional JSON serializer options. Defaults to <see cref="GitHubCopilotJsonUtilities.DefaultOptions"/>.</param>
    /// <param name="loggerFactory">Optional logger factory used to create the agent's logger.</param>
    /// <remarks>
    /// When a tool wrapped in <see cref="ApprovalRequiredAIFunction"/> is registered, the agent installs a default
    /// <c>Hooks.OnPreToolUse</c> handler that returns <c>"ask"</c> for those tools (routing the decision to
    /// <c>SessionConfig.OnPermissionRequest</c>) and defers all other tools.
    /// </remarks>
    public GitHubCopilotAgent(
        CopilotClient copilotClient,
        bool ownsClient = false,
        string? id = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        string? instructions = null,
        JsonSerializerOptions? jsonSerializerOptions = null,
        ILoggerFactory? loggerFactory = null)
        : this(
            copilotClient,
            GetSessionConfig(tools, instructions),
            ownsClient,
            id,
            name,
            description,
            jsonSerializerOptions,
            loggerFactory)
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

        // Create or resume a session with streaming enabled by default
        SessionConfig sessionConfig = this._sessionConfig != null
            ? CopySessionConfig(this._sessionConfig)
            : new SessionConfig { Streaming = true };

        bool isStreaming = sessionConfig.Streaming ?? true;
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
            using IDisposable subscription = copilotSession.On<SessionEvent>(evt =>
            {
                switch (evt)
                {
                    case AssistantMessageDeltaEvent deltaEvent:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(deltaEvent));
                        break;

                    case AssistantMessageEvent assistantMessage:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(assistantMessage, isStreaming));
                        break;

                    case ToolExecutionStartEvent toolStart:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(toolStart));
                        break;

                    case ToolExecutionCompleteEvent toolComplete:
                        channel.Writer.TryWrite(this.ConvertToAgentResponseUpdate(toolComplete));
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
                (List<AttachmentFile>? attachments, tempDir) = await ProcessDataContentAttachmentsAsync(
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
        await this._copilotClient.StartAsync(cancellationToken).ConfigureAwait(false);
    }

    private ResumeSessionConfig CreateResumeConfig()
    {
        return CopyResumeSessionConfig(this._sessionConfig);
    }

    /// <summary>
    /// Copies all supported properties from a source <see cref="SessionConfig"/> into a new instance,
    /// preserving <see cref="SessionConfigBase.Streaming"/> from the source (defaulting to <c>true</c> if unset).
    /// </summary>
    internal static SessionConfig CopySessionConfig(SessionConfig source)
    {
        SessionConfig copy = source.Clone();
        copy.Streaming = source.Streaming ?? true;
        return copy;
    }

    /// <summary>
    /// Copies all supported properties from a source <see cref="SessionConfig"/> into a new
    /// <see cref="ResumeSessionConfig"/>, preserving <see cref="SessionConfigBase.Streaming"/>
    /// from the source (defaulting to <c>true</c> if unset).
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
            ConfigDirectory = source?.ConfigDirectory,
            McpServers = source?.McpServers,
            CustomAgents = source?.CustomAgents,
            SkillDirectories = source?.SkillDirectories,
            DisabledSkills = source?.DisabledSkills,
            InfiniteSessions = source?.InfiniteSessions,
            Streaming = source?.Streaming ?? true
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

    /// <summary>
    /// Converts an <see cref="AssistantMessageEvent"/> to an <see cref="AgentResponseUpdate"/>.
    /// When streaming is enabled, text was already delivered via delta events, so only raw metadata is emitted.
    /// When streaming is disabled, the full message text is emitted as <see cref="TextContent"/>.
    /// </summary>
    internal AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantMessageEvent assistantMessage, bool isStreaming)
    {
        // When streaming, text was already delivered via AssistantMessageDeltaEvent.
        // When not streaming, this is the only opportunity to emit the response text.
        AIContent content = isStreaming
            ? new AIContent { RawRepresentation = assistantMessage }
            : new TextContent(assistantMessage.Data?.Content ?? string.Empty) { RawRepresentation = assistantMessage };

        return new AgentResponseUpdate(ChatRole.Assistant, [content])
        {
            AgentId = this.Id,
            ResponseId = assistantMessage.Data?.MessageId,
            MessageId = assistantMessage.Data?.MessageId,
            CreatedAt = assistantMessage.Timestamp
        };
    }

    internal AgentResponseUpdate ConvertToAgentResponseUpdate(ToolExecutionStartEvent toolStart)
    {
        IDictionary<string, object?>? arguments = this.ParseArguments(toolStart.Data?.Arguments);

        FunctionCallContent content = new(
            toolStart.Data?.ToolCallId ?? string.Empty,
            toolStart.Data?.ToolName ?? string.Empty,
            arguments)
        {
            RawRepresentation = toolStart
        };

        return new AgentResponseUpdate(ChatRole.Assistant, [content])
        {
            AgentId = this.Id,
            CreatedAt = toolStart.Timestamp
        };
    }

    internal AgentResponseUpdate ConvertToAgentResponseUpdate(ToolExecutionCompleteEvent toolComplete)
    {
        object? result = toolComplete.Data?.Success == true
            ? toolComplete.Data?.Result?.Content
            : toolComplete.Data?.Error?.Message ?? "Tool execution failed";

        FunctionResultContent content = new(
            toolComplete.Data?.ToolCallId ?? string.Empty,
            result)
        {
            RawRepresentation = toolComplete
        };

        return new AgentResponseUpdate(ChatRole.Tool, [content])
        {
            AgentId = this.Id,
            CreatedAt = toolComplete.Timestamp
        };
    }

    private IDictionary<string, object?>? ParseArguments(object? arguments)
    {
        if (arguments is null)
        {
            return null;
        }

        if (arguments is JsonElement jsonElement)
        {
            if (jsonElement.ValueKind == JsonValueKind.Null || jsonElement.ValueKind == JsonValueKind.Undefined)
            {
                return null;
            }

            var typeInfo = (JsonTypeInfo<Dictionary<string, object?>>)this._jsonSerializerOptions.GetTypeInfo(typeof(Dictionary<string, object?>));

            try
            {
                return JsonSerializer.Deserialize(jsonElement.GetRawText(), typeInfo);
            }
            catch (JsonException)
            {
                return new Dictionary<string, object?> { ["value"] = jsonElement.ToString() };
            }
        }

        if (arguments is IDictionary<string, object?> dict)
        {
            return dict;
        }

        return new Dictionary<string, object?> { ["value"] = arguments.ToString() };
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

        if (usageEvent.Data.CacheWriteTokens is long cacheWriteTokens)
        {
            additionalCounts ??= [];
            additionalCounts[nameof(AssistantUsageData.CacheWriteTokens)] = cacheWriteTokens;
        }

        if (usageEvent.Data.Cost is double cost)
        {
            additionalCounts ??= [];
            additionalCounts[nameof(AssistantUsageData.Cost)] = (long)cost;
        }

        if (usageEvent.Data.Duration is TimeSpan duration)
        {
            additionalCounts ??= [];
            additionalCounts[nameof(AssistantUsageData.Duration)] = (long)duration.TotalMilliseconds;
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
        List<AIFunctionDeclaration>? mappedTools = tools is { Count: > 0 } ? tools.OfType<AIFunctionDeclaration>().ToList() : null;
        SystemMessageConfig? systemMessage = instructions is not null ? new SystemMessageConfig { Mode = SystemMessageMode.Append, Content = instructions } : null;

        if (mappedTools is null && systemMessage is null)
        {
            return null;
        }

        return new SessionConfig { Tools = mappedTools, SystemMessage = systemMessage };
    }

    /// <summary>
    /// Installs a default <c>OnPreToolUse</c> hook that gates tools wrapped in <see cref="ApprovalRequiredAIFunction"/>
    /// by returning <c>"ask"</c> (routing the decision to <c>SessionConfig.OnPermissionRequest</c>) while deferring all
    /// other tools, so the GitHub Copilot SDK enforces approval through its native pre-tool-use hook.
    /// </summary>
    /// <remarks>
    /// The source <paramref name="sessionConfig"/> is returned unchanged when it contains no approval-required tools.
    /// If the caller already supplied a <c>Hooks.OnPreToolUse</c> handler, it takes precedence and is left untouched; a
    /// warning is logged for any approval-required tool that will therefore not be automatically gated. Otherwise a
    /// clone is returned (with a fresh <see cref="SessionHooks"/>) so the caller-supplied configuration is not mutated.
    /// </remarks>
    private static SessionConfig? ConfigureApprovalHook(SessionConfig? sessionConfig, ILogger logger)
    {
        if (sessionConfig?.Tools is not { Count: > 0 } tools)
        {
            return sessionConfig;
        }

        HashSet<string> approvalRequiredToolNames = new(StringComparer.Ordinal);
        foreach (AIFunctionDeclaration tool in tools)
        {
            if (tool is AIFunction function && function.GetService<ApprovalRequiredAIFunction>() is not null)
            {
                approvalRequiredToolNames.Add(function.Name);
            }
        }

        if (approvalRequiredToolNames.Count == 0)
        {
            return sessionConfig;
        }

        // A caller-supplied OnPreToolUse hook takes precedence and is fully responsible for approval handling.
        // Warn so the developer knows the ApprovalRequiredAIFunction marker(s) will not be automatically gated.
        if (sessionConfig.Hooks?.OnPreToolUse is not null)
        {
            if (logger.IsEnabled(LogLevel.Warning))
            {
                logger.LogApprovalGatingSkippedDueToCustomHook(
                    approvalRequiredToolNames.Count,
                    string.Join(", ", approvalRequiredToolNames));
            }
            return sessionConfig;
        }

        SessionConfig configured = sessionConfig.Clone();

        // SessionConfig.Clone() shallow-copies Hooks, so build a fresh SessionHooks (preserving any other hooks)
        // to avoid mutating the caller's instance when setting OnPreToolUse.
        SessionHooks hooks = CloneHooks(configured.Hooks);
        hooks.OnPreToolUse = (input, invocation) =>
            Task.FromResult(
                approvalRequiredToolNames.Contains(input.ToolName)
                    ? new PreToolUseHookOutput
                    {
                        PermissionDecision = "ask",
                        PermissionDecisionReason = $"Tool '{input.ToolName}' is marked as requiring approval (ApprovalRequiredAIFunction).",
                    }
                    : null);
        configured.Hooks = hooks;

        return configured;
    }

    /// <summary>
    /// Creates a shallow copy of a <see cref="SessionHooks"/> instance, preserving all configured hook delegates.
    /// </summary>
    private static SessionHooks CloneHooks(SessionHooks? source)
    {
        SessionHooks clone = new();
        if (source is not null)
        {
            clone.OnPreToolUse = source.OnPreToolUse;
            clone.OnPreMcpToolCall = source.OnPreMcpToolCall;
            clone.OnPostToolUse = source.OnPostToolUse;
            clone.OnPostToolUseFailure = source.OnPostToolUseFailure;
            clone.OnUserPromptSubmitted = source.OnUserPromptSubmitted;
            clone.OnSessionStart = source.OnSessionStart;
            clone.OnSessionEnd = source.OnSessionEnd;
            clone.OnErrorOccurred = source.OnErrorOccurred;
        }

        return clone;
    }

    private static async Task<(List<AttachmentFile>? Attachments, string? TempDir)> ProcessDataContentAttachmentsAsync(
        IEnumerable<ChatMessage> messages,
        CancellationToken cancellationToken)
    {
        List<AttachmentFile>? attachments = null;
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
                    attachments.Add(new AttachmentFile
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
