// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

/// <summary>
/// Executor for the <see cref="InvokeMcpTool"/> action.
/// This executor invokes MCP tools on remote servers and handles approval flows.
/// </summary>
internal sealed class InvokeMcpToolExecutor(
    InvokeMcpTool model,
    IMcpToolHandler mcpToolHandler,
    ResponseAgentProvider agentProvider,
    WorkflowFormulaState state) :
    DeclarativeActionExecutor<InvokeMcpTool>(model, state)
{
    private const string ApprovalSnapshotStateKey = nameof(_approvalSnapshots);
    private const string LegacyApprovalSnapshotStateKey = "_approvalSnapshot";
    private const string ListToolsToolName = "tools/list";

    /// <summary>
    /// Snapshots of evaluated parameters captured at approval-request time, keyed by
    /// per-invocation request id. Each pending approval lives here until the matching
    /// response is captured.
    /// </summary>
    private readonly ConcurrentDictionary<string, ApprovalSnapshot> _approvalSnapshots = new(StringComparer.Ordinal);

    /// <summary>
    /// Header values captured at approval-request time. These snapshots are intentionally
    /// kept in memory only so transport credentials are never persisted to workflow state.
    /// </summary>
    private readonly ConcurrentDictionary<string, HeaderSnapshot> _approvalHeaderSnapshots = new(StringComparer.Ordinal);

    /// <summary>
    /// Step identifiers for the MCP tool invocation workflow.
    /// </summary>
    public static class Steps
    {
        /// <summary>
        /// Step for waiting for external input (approval or direct response).
        /// </summary>
        public static string ExternalInput(string id) => $"{id}_{nameof(ExternalInput)}";

        /// <summary>
        /// Step for resuming after receiving external input.
        /// </summary>
        public static string Resume(string id) => $"{id}_{nameof(Resume)}";
    }

    /// <summary>
    /// Determines if the message indicates external input is required.
    /// </summary>
    public static bool RequiresInput(object? message) =>
        message is ExternalInputRequest || (message is PortableValue pv && pv.IsType(out ExternalInputRequest? _));

    /// <summary>
    /// Determines if the message indicates no external input is required.
    /// </summary>
    public static bool RequiresNothing(object? message) =>
        message is ActionExecutorResult || (message is PortableValue pv && pv.IsType(out ActionExecutorResult? _));

    /// <inheritdoc/>
    protected override bool EmitResultEvent => false;

    /// <inheritdoc/>
    protected override bool IsDiscreteAction => false;

    /// <inheritdoc/>
    [SendsMessage(typeof(ExternalInputRequest))]
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string serverUrl = this.GetServerUrl();
        string? serverLabel = this.GetServerLabel();
        string toolName = this.GetToolName();
        bool requireApproval = this.GetRequireApproval();
        bool autoSend = this.GetAutoSendValue();
        Dictionary<string, object?>? arguments = this.GetArguments();
        Dictionary<string, string>? headers = this.GetHeaders();
        string? conversationId = this.GetConversationId();
        string? connectionName = this.GetConnectionName();

        if (requireApproval)
        {
            await this.RequestApprovalAsync(
                context,
                serverUrl,
                serverLabel,
                toolName,
                arguments,
                headers,
                connectionName,
                autoSend,
                cancellationToken).ConfigureAwait(false);
            return default;
        }

        // No approval required - invoke the tool directly
        McpServerToolResultContent resultContent = await mcpToolHandler.InvokeToolAsync(
            serverUrl,
            serverLabel,
            toolName,
            arguments,
            headers,
            connectionName,
            cancellationToken).ConfigureAwait(false);

        await this.ProcessResultAsync(context, resultContent, conversationId, autoSend, cancellationToken).ConfigureAwait(false);

        // Signal completion so the workflow routes via RequiresNothing
        await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);

        return default;
    }

    /// <summary>
    /// Captures the external input response and processes the MCP tool result.
    /// </summary>
    /// <param name="context">The workflow context.</param>
    /// <param name="response">The external input response.</param>
    /// <param name="cancellationToken">A cancellation token.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    [SendsMessage(typeof(ExternalInputRequest))]
    [SendsMessage(typeof(ActionExecutorResult))]
    public async ValueTask CaptureResponseAsync(
        IWorkflowContext context,
        ExternalInputResponse response,
        CancellationToken cancellationToken)
    {
        ToolApprovalResponseContent? approvalResponse = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalResponseContent>()
            .FirstOrDefault(r => this._approvalSnapshots.ContainsKey(r.RequestId));

        if (approvalResponse is null)
        {
            await this.AssignErrorAsync(context, "No pending approval matched the response.").ConfigureAwait(false);
            await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
            return;
        }

        if (!approvalResponse.Approved)
        {
            this._approvalSnapshots.TryRemove(approvalResponse.RequestId, out _);
            this._approvalHeaderSnapshots.TryRemove(approvalResponse.RequestId, out _);
            await this.AssignErrorAsync(context, "MCP tool invocation was not approved by user.").ConfigureAwait(false);
            await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
            return;
        }

        if (!this._approvalSnapshots.TryRemove(approvalResponse.RequestId, out ApprovalSnapshot? snapshot))
        {
            await this.AssignErrorAsync(context, "No pending approval matched the response.").ConfigureAwait(false);
            await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
            return;
        }

        if (snapshot.ConnectionName is not null && !snapshot.ConnectionNameValidated)
        {
            this._approvalHeaderSnapshots.TryRemove(approvalResponse.RequestId, out _);
            await this.RequestApprovalAsync(context, snapshot.AutoSend, cancellationToken).ConfigureAwait(false);
            return;
        }

        Dictionary<string, string>? headers;
        if (this._approvalHeaderSnapshots.TryRemove(approvalResponse.RequestId, out HeaderSnapshot? headerSnapshot))
        {
            headers = headerSnapshot.Headers;
        }
        else if (snapshot.RequiresHeaderReapprovalAfterRestore || this.Model.Headers is { Count: > 0 })
        {
            await this.RequestApprovalAsync(context, snapshot.AutoSend, cancellationToken).ConfigureAwait(false);
            return;
        }
        else
        {
            headers = null;
        }

        if (!snapshot.IsDiscoveryApproval &&
            !snapshot.DiscoveryApproved &&
            !string.Equals(snapshot.ToolName, ListToolsToolName, StringComparison.Ordinal))
        {
            string reapprovalNotice = snapshot.ToolDefinitionFingerprint is null
                ? "The previous approval did not include the MCP tool definition. Review the request before approving."
                : "The previous approval did not include separate MCP tool discovery consent. Review the request before approving.";
            await this.RequestApprovalAsync(
                context,
                snapshot.ServerUrl,
                snapshot.ServerLabel,
                snapshot.ToolName,
                snapshot.Arguments,
                headers,
                snapshot.ConnectionName,
                snapshot.AutoSend ?? this.GetAutoSendValue(),
                cancellationToken,
                reapprovalNotice).ConfigureAwait(false);
            return;
        }

        string? conversationId = this.GetConversationId();
        if (!string.Equals(snapshot.ToolName, ListToolsToolName, StringComparison.Ordinal))
        {
            string currentToolDefinitionFingerprint = await this.GetToolDefinitionFingerprintAsync(
                snapshot.ServerUrl,
                snapshot.ServerLabel,
                snapshot.ToolName,
                headers,
                snapshot.ConnectionName,
                cancellationToken).ConfigureAwait(false);
            if (snapshot.IsDiscoveryApproval ||
                !string.Equals(snapshot.ToolDefinitionFingerprint, currentToolDefinitionFingerprint, StringComparison.Ordinal))
            {
                string? reapprovalNotice = snapshot.IsDiscoveryApproval
                    ? null
                    : snapshot.ToolDefinitionFingerprint is null
                        ? "The previous approval did not include the MCP tool definition. Review the request before approving."
                        : "The MCP tool definition changed since the previous approval. Review the request before approving.";
                await this.RequestApprovalAsync(
                    context,
                    snapshot.ServerUrl,
                    snapshot.ServerLabel,
                    snapshot.ToolName,
                    snapshot.Arguments,
                    headers,
                    snapshot.ConnectionName,
                    snapshot.AutoSend ?? this.GetAutoSendValue(),
                    cancellationToken,
                    reapprovalNotice,
                    currentToolDefinitionFingerprint).ConfigureAwait(false);
                return;
            }
        }

        bool autoSend = snapshot.AutoSend ?? this.GetAutoSendValue();
        McpServerToolResultContent resultContent = await mcpToolHandler.InvokeToolAsync(
            snapshot.ServerUrl,
            snapshot.ServerLabel,
            snapshot.ToolName,
            snapshot.Arguments,
            headers,
            snapshot.ConnectionName,
            cancellationToken).ConfigureAwait(false);

        await this.ProcessResultAsync(context, resultContent, conversationId, autoSend, cancellationToken).ConfigureAwait(false);
        await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Completes the MCP tool invocation by raising the completion event.
    /// </summary>
    public async ValueTask CompleteAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
    {
        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override ValueTask ResetAsync()
    {
        this._approvalSnapshots.Clear();
        this._approvalHeaderSnapshots.Clear();
        return default;
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Persists pending approval snapshots to workflow state so they survive
    /// checkpoint/restore cycles.
    /// </remarks>
    protected override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Dictionary<string, ApprovalSnapshot> snapshotCopy = this._approvalSnapshots.ToDictionary(kvp => kvp.Key, kvp => kvp.Value, StringComparer.Ordinal);
        await context.QueueStateUpdateAsync(ApprovalSnapshotStateKey, snapshotCopy, null, cancellationToken).ConfigureAwait(false);
        await base.OnCheckpointingAsync(context, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Restores pending approval snapshots from workflow state after a checkpoint restore.
    /// </remarks>
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);

        this._approvalSnapshots.Clear();
        this._approvalHeaderSnapshots.Clear();
        Dictionary<string, ApprovalSnapshot>? snapshots = await context.ReadStateAsync<Dictionary<string, ApprovalSnapshot>>(
            ApprovalSnapshotStateKey, null, cancellationToken).ConfigureAwait(false);
        if (snapshots is not null)
        {
            foreach (KeyValuePair<string, ApprovalSnapshot> entry in snapshots)
            {
                this._approvalSnapshots[entry.Key] = entry.Value;
            }
        }

        // Migrate a single ApprovalSnapshot at the legacy key under this.Id so the
        // legacy approval response matches the per-invocation map; clear the legacy key.
        ApprovalSnapshot? legacy = await context.ReadStateAsync<ApprovalSnapshot>(
            LegacyApprovalSnapshotStateKey, null, cancellationToken).ConfigureAwait(false);
        if (legacy is not null)
        {
            this._approvalSnapshots.TryAdd(this.Id, legacy);
            await context.QueueStateUpdateAsync<ApprovalSnapshot?>(
                LegacyApprovalSnapshotStateKey, null, null, cancellationToken).ConfigureAwait(false);
        }
    }

    private ValueTask RequestApprovalAsync(IWorkflowContext context, bool? autoSend, CancellationToken cancellationToken)
    {
        return this.RequestApprovalAsync(
            context,
            this.GetServerUrl(),
            this.GetServerLabel(),
            this.GetToolName(),
            this.GetArguments(),
            this.GetHeaders(),
            this.GetConnectionName(),
            autoSend ?? this.GetAutoSendValue(),
            cancellationToken);
    }

    private async ValueTask RequestApprovalAsync(
        IWorkflowContext context,
        string serverUrl,
        string? serverLabel,
        string toolName,
        Dictionary<string, object?>? arguments,
        Dictionary<string, string>? headers,
        string? connectionName,
        bool autoSend,
        CancellationToken cancellationToken,
        string? reapprovalNotice = null,
        string? toolDefinitionFingerprint = null)
    {
        bool isListTools = string.Equals(toolName, ListToolsToolName, StringComparison.Ordinal);
        bool isDiscoveryApproval = toolDefinitionFingerprint is null && !isListTools;
        string requestId = Guid.NewGuid().ToString("N");

        this._approvalSnapshots[requestId] = new ApprovalSnapshot(serverUrl, serverLabel, toolName, arguments, connectionName)
        {
            ConnectionNameValidated = true,
            RequiresHeaderReapprovalAfterRestore = this.Model.Headers is { Count: > 0 },
            AutoSend = autoSend,
            ToolDefinitionFingerprint = toolDefinitionFingerprint,
            IsDiscoveryApproval = isDiscoveryApproval,
            DiscoveryApproved = toolDefinitionFingerprint is not null,
        };
        this._approvalHeaderSnapshots[requestId] = new HeaderSnapshot(headers);

        // Transport headers are intentionally excluded from externally-surfaced approval content.
        string approvalServerName = isDiscoveryApproval || isListTools ? serverUrl : serverLabel ?? serverUrl;
        McpServerToolCallContent toolCall = new(requestId, isDiscoveryApproval ? ListToolsToolName : toolName, approvalServerName)
        {
            Arguments = isDiscoveryApproval ? null : arguments
        };

        ToolApprovalRequestContent approvalRequest = new(requestId, toolCall);
        if (isDiscoveryApproval || isListTools)
        {
            string discoveryNotice = $"Allow MCP tool discovery at '{serverUrl}' using the configured transport settings.";
            if (isDiscoveryApproval)
            {
                discoveryNotice += $" This does not approve invoking '{toolName}'; a separate tool approval will follow discovery.";
            }

            reapprovalNotice = reapprovalNotice is null ? discoveryNotice : $"{reapprovalNotice} {discoveryNotice}";
        }

        ChatMessage requestMessage = reapprovalNotice is not null
            ? new ChatMessage(ChatRole.Assistant, [new TextContent(reapprovalNotice), approvalRequest])
            : new ChatMessage(ChatRole.Assistant, [approvalRequest]);
        await context.SendMessageAsync(new ExternalInputRequest(new AgentResponse([requestMessage])), cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask<string> GetToolDefinitionFingerprintAsync(
        string serverUrl,
        string? serverLabel,
        string toolName,
        IDictionary<string, string>? headers,
        string? connectionName,
        CancellationToken cancellationToken)
    {
        McpServerToolResultContent toolList = await mcpToolHandler.InvokeToolAsync(
            serverUrl,
            serverLabel,
            ListToolsToolName,
            null,
            headers,
            connectionName,
            cancellationToken).ConfigureAwait(false);

        string? matchingToolFingerprint = null;
        bool foundToolsArray = false;
        if (toolList.Outputs is not null)
        {
            foreach (TextContent textContent in toolList.Outputs.OfType<TextContent>())
            {
                string serialized = textContent.Text.TrimStart();
                if (serialized.Length == 0 || serialized[0] != '{')
                {
                    continue;
                }

                using JsonDocument document = JsonDocument.Parse(serialized);
                if (!document.RootElement.TryGetProperty("tools", out JsonElement tools) ||
                    tools.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                foundToolsArray = true;
                foreach (JsonElement tool in tools.EnumerateArray())
                {
                    if (tool.TryGetProperty("name", out JsonElement name) &&
                        name.ValueKind == JsonValueKind.String &&
                        string.Equals(name.GetString(), toolName, StringComparison.Ordinal))
                    {
                        if (matchingToolFingerprint is not null)
                        {
                            throw this.Exception($"The MCP server returned multiple definitions for tool '{toolName}'.");
                        }

                        matchingToolFingerprint = ComputeToolDefinitionFingerprint(tool);
                    }
                }
            }
        }

        if (!foundToolsArray)
        {
            throw this.Exception($"The MCP server did not return a valid tool list while checking approval for tool '{toolName}'.");
        }

        if (matchingToolFingerprint is null)
        {
            throw this.Exception($"The MCP server did not return a definition for tool '{toolName}'.");
        }

        return matchingToolFingerprint;
    }

    private static string ComputeToolDefinitionFingerprint(JsonElement tool)
    {
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream))
        {
            WriteCanonicalJson(writer, tool);
        }

#if NET
        return Convert.ToHexString(SHA256.HashData(stream.ToArray()));
#else
        using SHA256 sha256 = SHA256.Create();
        return BitConverter.ToString(sha256.ComputeHash(stream.ToArray())).Replace("-", string.Empty);
#endif
    }

    private static void WriteCanonicalJson(Utf8JsonWriter writer, JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (JsonProperty property in value.EnumerateObject().OrderBy(property => property.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    WriteCanonicalJson(writer, property.Value);
                }

                writer.WriteEndObject();
                break;

            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (JsonElement element in value.EnumerateArray())
                {
                    WriteCanonicalJson(writer, element);
                }

                writer.WriteEndArray();
                break;

            default:
                value.WriteTo(writer);
                break;
        }
    }

    private async ValueTask ProcessResultAsync(
        IWorkflowContext context,
        McpServerToolResultContent resultContent,
        string? conversationId,
        bool autoSend,
        CancellationToken cancellationToken)
    {
        await this.AssignResultAsync(context, resultContent).ConfigureAwait(false);
        ChatMessage resultMessage = new(ChatRole.Tool, resultContent.Outputs);

        // Store messages if output path is configured
        if (this.Model.Output?.Messages is not null)
        {
            await this.AssignAsync(this.Model.Output.Messages?.Path, resultMessage.ToFormula(), context).ConfigureAwait(false);
        }

        // Auto-send the result if configured
        if (autoSend)
        {
            AgentResponse resultResponse = new([resultMessage]);
            await context.AddEventAsync(new AgentResponseEvent(this.Id, resultResponse), cancellationToken).ConfigureAwait(false);
        }

        // Add messages to conversation if conversationId is provided
        if (conversationId is not null)
        {
            ChatMessage assistantMessage = new(ChatRole.Assistant, resultContent.Outputs);
            await agentProvider.CreateMessageAsync(conversationId, assistantMessage, cancellationToken).ConfigureAwait(false);
        }
    }

    private async ValueTask AssignResultAsync(IWorkflowContext context, McpServerToolResultContent toolResult)
    {
        if (this.Model.Output?.Result is null || toolResult.Outputs is null || toolResult.Outputs.Count == 0)
        {
            return;
        }

        List<object?> parsedResults = [];
        foreach (AIContent resultContent in toolResult.Outputs)
        {
            object? resultValue = resultContent switch
            {
                TextContent text => text.Text,
                DataContent data => data.Uri,
                _ => resultContent.ToString(),
            };

            // Convert JsonElement to its raw JSON string for processing
            if (resultValue is JsonElement jsonElement)
            {
                resultValue = jsonElement.GetRawText();
            }

            // Attempt to parse as JSON if it's a string (or was converted from JsonElement)
            if (resultValue is string jsonString)
            {
                try
                {
                    using JsonDocument jsonDocument = JsonDocument.Parse(jsonString);

                    // Handle different JSON value kinds
                    object? parsedValue = jsonDocument.ParseJsonValue(jsonString);

                    parsedResults.Add(parsedValue);
                    continue;
                }
                catch (JsonException)
                {
                    // Not a valid JSON
                }
            }

            parsedResults.Add(resultValue);
        }

        await this.AssignAsync(this.Model.Output.Result?.Path, parsedResults.ToFormula(), context).ConfigureAwait(false);
    }

    private async ValueTask AssignErrorAsync(IWorkflowContext context, string errorMessage)
    {
        // Store error in result if configured (as a simple string)
        if (this.Model.Output?.Result is not null)
        {
            await this.AssignAsync(this.Model.Output.Result?.Path, $"Error: {errorMessage}".ToFormula(), context).ConfigureAwait(false);
        }
    }

    private string GetServerUrl() =>
        this.GetInvocationValue(
            this.Evaluator.GetValue(
                Throw.IfNull(
                    this.Model.ServerUrl,
                    $"{nameof(this.Model)}.{nameof(this.Model.ServerUrl)}")),
            "server URL");

    private string? GetServerLabel()
    {
        if (this.Model.ServerLabel is null)
        {
            return null;
        }

        string value = this.GetInvocationValue(this.Evaluator.GetValue(this.Model.ServerLabel), "server label");
        return value.Length == 0 ? null : value;
    }

    private string GetToolName() =>
        this.GetInvocationValue(
            this.Evaluator.GetValue(
                Throw.IfNull(
                    this.Model.ToolName,
                    $"{nameof(this.Model)}.{nameof(this.Model.ToolName)}")),
            "tool name");

    private string? GetConversationId()
    {
        if (this.Model.ConversationId is null)
        {
            return null;
        }

        string value = this.GetNonSensitiveValue(
            this.Evaluator.GetValue(this.Model.ConversationId),
            ConversationIdLocation);
        return value.Length == 0 ? null : value;
    }

    private bool GetRequireApproval()
    {
        if (this.Model.RequireApproval is null)
        {
            return false;
        }

        return this.GetNonSensitiveValue(this.Evaluator.GetValue(this.Model.RequireApproval), "require approval");
    }

    private bool GetAutoSendValue()
    {
        // InvokeToolOutput.AutoSend is never null — it returns a literal-false default
        // when the YAML omits the field. Use AutoSendIsDefaultValue to distinguish an
        // explicit autoSend value from the implicit default, and treat the implicit
        // default as autoSend = true (the historical behavior).
        if (this.Model.Output is { AutoSendIsDefaultValue: false } output)
        {
            return this.GetNonSensitiveValue(this.Evaluator.GetValue(output.AutoSend), "auto send");
        }

        return true;
    }

    private string? GetConnectionName()
    {
        if (this.Model.Connection?.Name is null)
        {
            return null;
        }

        string value = this.GetNonSensitiveValue(
            this.Evaluator.GetValue(this.Model.Connection.Name),
            ConnectionNameLocation);
        return value.Length == 0 ? null : value;
    }

    private Dictionary<string, object?>? GetArguments()
    {
        if (this.Model.Arguments is null)
        {
            return null;
        }

        Dictionary<string, object?> result = [];
        foreach (KeyValuePair<string, ValueExpression> argument in this.Model.Arguments)
        {
            result[argument.Key] = this.GetInvocationValue(
                this.Evaluator.GetValue(argument.Value),
                $"argument '{argument.Key}'").ToObject();
        }

        return result;
    }

    private Dictionary<string, string>? GetHeaders()
    {
        if (this.Model.Headers is null)
        {
            return null;
        }

        Dictionary<string, string> result = new(StringComparer.OrdinalIgnoreCase);
        foreach (KeyValuePair<string, StringExpression> header in this.Model.Headers)
        {
            string value = this.GetInvocationValue(
                this.Evaluator.GetValue(header.Value),
                $"header '{header.Key}'");
            if (!string.IsNullOrEmpty(value))
            {
                result[header.Key] = value;
            }
        }

        return result;
    }

    private T GetInvocationValue<T>(EvaluationResult<T> result, string location)
    {
        if (result.Sensitivity == SensitivityLevel.Sensitive)
        {
            throw this.Exception($"Cannot use a protected value in MCP tool invocation {location}.");
        }

        return result.Value;
    }

    /// <summary>
    /// Captured invocation parameters used by <see cref="CaptureResponseAsync"/> on
    /// resume so the approved values are invoked regardless of subsequent state changes.
    /// </summary>
    internal sealed record ApprovalSnapshot(
        string ServerUrl,
        string? ServerLabel,
        string ToolName,
        Dictionary<string, object?>? Arguments,
        string? ConnectionName)
    {
        public bool? AutoSend { get; init; }

        public bool ConnectionNameValidated { get; init; }

        public bool RequiresHeaderReapprovalAfterRestore { get; init; }

        public string? ToolDefinitionFingerprint { get; init; }

        public bool IsDiscoveryApproval { get; init; }

        public bool DiscoveryApproved { get; init; }
    }

    private sealed record HeaderSnapshot(Dictionary<string, string>? Headers);
}
