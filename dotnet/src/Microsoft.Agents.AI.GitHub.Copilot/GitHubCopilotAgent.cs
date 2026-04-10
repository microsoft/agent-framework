// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
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

    /// <summary>
    /// Key used in <see cref="FunctionCallContent"/> AdditionalProperties to mark a tool call
    /// as requiring AG-UI human-in-the-loop approval. The value is the approval request ID.
    /// </summary>
    internal const string ApprovalRequestIdKey = "ag_ui_approval_request_id";

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

        // Create channel FIRST so it's available for the OnPermissionRequest closure
        Channel<AgentResponseUpdate> channel = Channel.CreateUnbounded<AgentResponseUpdate>();

        // Extract HITL approval registration delegate from run options, if provided by MapAGUI
        Func<string, Task<bool>>? approvalRegistration = null;
        if (options?.AdditionalProperties?.TryGetValue("ag_ui_pending_approval_store", out object? storeObj) == true
            && storeObj is Func<string, Task<bool>> registrationFunc)
        {
            approvalRegistration = registrationFunc;
            Trace.TraceInformation("[AGUI-Permission] HITL approval delegate found in AdditionalProperties — Phase 2 enabled");
        }
        else
        {
            Trace.TraceInformation("[AGUI-Permission] No HITL approval delegate — Phase 1 visibility-only mode");
        }

        // Wrap OnPermissionRequest to emit TOOL_CALL_* AG-UI events for MCP tool calls
        bool hasPermissionHandler = this._sessionConfig?.OnPermissionRequest is not null;
        Trace.TraceInformation("[AGUI-Permission] OnPermissionRequest handler present: {0}", hasPermissionHandler);

        // Create or resume a session with streaming enabled, wrapping OnPermissionRequest
        // to emit TOOL_CALL_* AG-UI events for MCP tool calls
        SessionConfig sessionConfig = this._sessionConfig != null
            ? CopySessionConfigWithPermissionEmitter(this._sessionConfig, channel.Writer, this.Id, approvalRegistration)
            : new SessionConfig { Streaming = true };

        // Verify the copied config actually has the handler set
        Trace.TraceInformation("[AGUI-Permission] SessionConfig after copy — OnPermissionRequest is {0}",
            sessionConfig.OnPermissionRequest is not null ? "SET (wrapped)" : "NULL");

        CopilotSession copilotSession;
        if (typedSession.SessionId is not null)
        {
            var resumeConfig = CopyResumeSessionConfigWithPermissionEmitter(this._sessionConfig, channel.Writer, this.Id, approvalRegistration);
            Trace.TraceInformation("[AGUI-Permission] ResumeSessionConfig — OnPermissionRequest is {0}",
                resumeConfig.OnPermissionRequest is not null ? "SET (wrapped)" : "NULL");
            copilotSession = await this._copilotClient.ResumeSessionAsync(
                typedSession.SessionId,
                resumeConfig,
                cancellationToken).ConfigureAwait(false);
        }
        else
        {
            copilotSession = await this._copilotClient.CreateSessionAsync(sessionConfig, cancellationToken).ConfigureAwait(false);
            typedSession.SessionId = copilotSession.SessionId;
        }

        Trace.TraceInformation("[AGUI-Permission] Copilot session created: SessionId={0}", copilotSession.SessionId);

        try
        {
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
                        Trace.TraceInformation("[AGUI-Permission] session.On DEFAULT branch — event type: {0}", evt.GetType().Name);
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
    /// Copies a <see cref="SessionConfig"/> and wraps <see cref="SessionConfig.OnPermissionRequest"/>
    /// to emit <see cref="FunctionCallContent"/> and <see cref="FunctionResultContent"/> into the AG-UI
    /// event stream, providing tool call visibility for MCP and other permission-gated tool calls.
    /// </summary>
    internal static SessionConfig CopySessionConfigWithPermissionEmitter(
        SessionConfig source,
        ChannelWriter<AgentResponseUpdate> channelWriter,
        string? agentId,
        Func<string, Task<bool>>? approvalRegistration = null)
    {
        SessionConfig copy = CopySessionConfig(source);
        copy.OnPermissionRequest = WrapPermissionHandler(source.OnPermissionRequest, channelWriter, agentId, approvalRegistration);
        return copy;
    }

    /// <summary>
    /// Copies a <see cref="SessionConfig"/> into a <see cref="ResumeSessionConfig"/> and wraps
    /// <see cref="ResumeSessionConfig.OnPermissionRequest"/> to emit tool call events.
    /// </summary>
    internal static ResumeSessionConfig CopyResumeSessionConfigWithPermissionEmitter(
        SessionConfig? source,
        ChannelWriter<AgentResponseUpdate> channelWriter,
        string? agentId,
        Func<string, Task<bool>>? approvalRegistration = null)
    {
        ResumeSessionConfig copy = CopyResumeSessionConfig(source);
        copy.OnPermissionRequest = WrapPermissionHandler(source?.OnPermissionRequest, channelWriter, agentId, approvalRegistration);
        return copy;
    }

    private static PermissionRequestHandler? WrapPermissionHandler(
        PermissionRequestHandler? originalHandler,
        ChannelWriter<AgentResponseUpdate> channelWriter,
        string? agentId)
    {
        return WrapPermissionHandler(originalHandler, channelWriter, agentId, approvalRegistration: null);
    }

    private static PermissionRequestHandler? WrapPermissionHandler(
        PermissionRequestHandler? originalHandler,
        ChannelWriter<AgentResponseUpdate> channelWriter,
        string? agentId,
        Func<string, Task<bool>>? approvalRegistration)
    {
        if (originalHandler is null)
        {
            return null;
        }

        return async (request, invocation) =>
        {
            string callId = Guid.NewGuid().ToString("N");
            string toolName = BuildToolName(request);

            Trace.TraceInformation("[AGUI-Permission] OnPermissionRequest fired: Kind={0}, ToolName={1}, CallId={2}", request.Kind, toolName, callId);

            // Emit FunctionCallContent so the AG-UI pipeline generates TOOL_CALL_START/ARGS/END
            bool written = channelWriter.TryWrite(BuildPermissionFunctionCallUpdate(callId, toolName, request, agentId));
            Trace.TraceInformation("[AGUI-Permission] FunctionCallContent written to channel: CallId={0}, Success={1}", callId, written);

            PermissionRequestResult result;

            if (approvalRegistration is not null)
            {
                Trace.TraceInformation("[AGUI-Permission] HITL mode — blocking for client approval: CallId={0}", callId);
                // HITL mode: block until the AG-UI client responds via the /approve endpoint
                bool approved = await approvalRegistration(callId).ConfigureAwait(false);
                Trace.TraceInformation("[AGUI-Permission] HITL approval resolved: CallId={0}, Approved={1}", callId, approved);
                result = new PermissionRequestResult
                {
                    Kind = approved ? PermissionRequestResultKind.Approved : PermissionRequestResultKind.DeniedInteractivelyByUser
                };
            }
            else
            {
                Trace.TraceInformation("[AGUI-Permission] Phase 1 mode — forwarding to original handler: CallId={0}", callId);
                // Forward to the caller's original handler (e.g., ApproveAll or server-side logic)
                result = await originalHandler(request, invocation).ConfigureAwait(false);
                Trace.TraceInformation("[AGUI-Permission] Original handler returned: CallId={0}, ResultKind={1}", callId, result.Kind);
            }

            // Emit FunctionResultContent so the AG-UI pipeline generates TOOL_CALL_RESULT
            bool resultWritten = channelWriter.TryWrite(BuildPermissionResultUpdate(callId, result, agentId));
            Trace.TraceInformation("[AGUI-Permission] FunctionResultContent written to channel: CallId={0}, ResultKind={1}, Success={2}", callId, result.Kind, resultWritten);

            return result;
        };
    }

    private static string BuildToolName(PermissionRequest request)
    {
        // Use typed subclass properties when available for richer tool names
        if (request is PermissionRequestMcp mcp && !string.IsNullOrEmpty(mcp.ToolName))
        {
            return !string.IsNullOrEmpty(mcp.ServerName)
                ? $"{mcp.ServerName}/{mcp.ToolName}"
                : mcp.ToolName;
        }

        return request.Kind ?? "unknown_tool";
    }

    private static AgentResponseUpdate BuildPermissionFunctionCallUpdate(
        string callId,
        string toolName,
        PermissionRequest request,
        string? agentId)
    {
        var args = new Dictionary<string, object?>
        {
            ["kind"] = request.Kind,
        };

        // Add typed properties from PermissionRequest subclasses
        if (request is PermissionRequestMcp mcp)
        {
            args["serverName"] = mcp.ServerName;
            args["toolName"] = mcp.ToolName;
            args["toolTitle"] = mcp.ToolTitle;
            args["readOnly"] = mcp.ReadOnly;
            if (mcp.Args is not null)
            {
                args["args"] = mcp.Args;
            }
        }
        else if (request is PermissionRequestShell shell)
        {
            args["fullCommandText"] = shell.FullCommandText;
        }
        else if (request is PermissionRequestWrite write)
        {
            args["fileName"] = write.FileName;
        }
        else if (request is PermissionRequestRead read)
        {
            args["path"] = read.Path;
        }
        else if (request is PermissionRequestUrl url)
        {
            args["url"] = url.Url;
        }

        FunctionCallContent callContent = new(callId, toolName, args)
        {
            RawRepresentation = request,
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                // Marker for the AG-UI pipeline to emit a CUSTOM tool_approval_requested event
                [ApprovalRequestIdKey] = callId,
            },
        };

        return new AgentResponseUpdate(ChatRole.Assistant, [callContent])
        {
            AgentId = agentId,
            MessageId = callId
        };
    }

    private static AgentResponseUpdate BuildPermissionResultUpdate(
        string callId,
        PermissionRequestResult result,
        string? agentId)
    {
        string resultText = result.Kind.ToString();
        FunctionResultContent resultContent = new(callId, resultText)
        {
            RawRepresentation = result,
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                // Marker for the AG-UI pipeline to emit a CUSTOM tool_approval_completed event
                [ApprovalRequestIdKey] = callId,
            },
        };

        return new AgentResponseUpdate(ChatRole.Tool, [resultContent])
        {
            AgentId = agentId,
            MessageId = callId
        };
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
            OnEvent = source.OnEvent,
            Hooks = source.Hooks,
            WorkingDirectory = source.WorkingDirectory,
            ConfigDir = source.ConfigDir,
            McpServers = source.McpServers,
            CustomAgents = source.CustomAgents,
            Agent = source.Agent,
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
            OnEvent = source?.OnEvent,
            Hooks = source?.Hooks,
            WorkingDirectory = source?.WorkingDirectory,
            ConfigDir = source?.ConfigDir,
            McpServers = source?.McpServers,
            CustomAgents = source?.CustomAgents,
            Agent = source?.Agent,
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

    internal AgentResponseUpdate ConvertToAgentResponseUpdate(AssistantMessageEvent assistantMessage)
    {
        AIContent content = new()
        {
            RawRepresentation = assistantMessage
        };

        return new AgentResponseUpdate(ChatRole.Assistant, [content])
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
