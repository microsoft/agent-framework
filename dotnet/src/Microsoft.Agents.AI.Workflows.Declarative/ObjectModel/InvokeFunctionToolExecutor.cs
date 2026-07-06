// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

/// <summary>
/// Executor for the <see cref="InvokeFunctionTool"/> action.
/// This executor yields to the caller for function execution and resumes when results are provided.
/// </summary>
internal sealed class InvokeFunctionToolExecutor(
    InvokeFunctionTool model,
    ResponseAgentProvider agentProvider,
    WorkflowFormulaState state) :
    DeclarativeActionExecutor<InvokeFunctionTool>(model, state)
{
    private const string ApprovalSnapshotStateKey = nameof(_approvalSnapshots);
    private const string PendingCallIdsStateKey = nameof(_pendingNonApprovalCallIds);
    private const string LegacyApprovalSnapshotStateKey = "_approvalSnapshot";

    /// <summary>
    /// Snapshots of evaluated parameters captured at approval-request time, keyed by
    /// per-invocation request id. Each pending approval lives here until the matching
    /// response is captured.
    /// </summary>
    private readonly ConcurrentDictionary<string, ApprovalSnapshot> _approvalSnapshots = new(StringComparer.Ordinal);

    /// <summary>
    /// Per-invocation call ids for in-flight non-approval requests; used to match the
    /// returning <see cref="FunctionResultContent"/> on the response path. Used as a set;
    /// the byte value is ignored.
    /// </summary>
    private readonly ConcurrentDictionary<string, byte> _pendingNonApprovalCallIds = new(StringComparer.Ordinal);

    /// <summary>
    /// Step identifiers for the function tool invocation workflow.
    /// </summary>
    public static class Steps
    {
        /// <summary>
        /// Step for waiting for external input (function result).
        /// </summary>
        public static string ExternalInput(string id) => $"{id}_{nameof(ExternalInput)}";

        /// <summary>
        /// Step for resuming after receiving function result.
        /// </summary>
        public static string Resume(string id) => $"{id}_{nameof(Resume)}";
    }

    /// <inheritdoc/>
    protected override bool EmitResultEvent => false;

    /// <inheritdoc/>
    protected override bool IsDiscreteAction => false;

    /// <inheritdoc/>
    [SendsMessage(typeof(ExternalInputRequest))]
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string functionName = this.GetFunctionName();
        bool requireApproval = this.GetRequireApproval();
        Dictionary<string, object?>? arguments = this.GetArguments();

        // Per-invocation request id stamped on the outbound content.
        string requestId = Guid.NewGuid().ToString("N");

        // Create the function call content to send to the caller
        FunctionCallContent functionCall = new(
            callId: requestId,
            name: functionName,
            arguments: arguments);

        // Build the response with the function call request
        ChatMessage requestMessage = new(ChatRole.Tool, [functionCall]);

        // If approval is required, add user input request content
        if (requireApproval)
        {
            // Capture the evaluated parameters keyed by request id; the matching response
            // resumes from this snapshot.
            this._approvalSnapshots[requestId] = new ApprovalSnapshot(functionName, arguments);

            requestMessage.Contents.Add(new ToolApprovalRequestContent(requestId, functionCall));
        }
        else
        {
            this._pendingNonApprovalCallIds.TryAdd(requestId, 0);
        }

        AgentResponse agentResponse = new([requestMessage]);

        // Yield to the caller - workflow halts here until external input is received
        ExternalInputRequest inputRequest = new(agentResponse);
        await context.SendMessageAsync(inputRequest, cancellationToken).ConfigureAwait(false);

        return default;
    }

    /// <summary>
    /// Captures the function result and stores in output variables.
    /// </summary>
    /// <param name="context">The workflow context.</param>
    /// <param name="response">The external input response containing the function result.</param>
    /// <param name="cancellationToken">A cancellation token.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    public async ValueTask CaptureResponseAsync(
        IWorkflowContext context,
        ExternalInputResponse response,
        CancellationToken cancellationToken)
    {
        bool autoSend = this.GetAutoSendValue();
        string? conversationId = this.GetConversationId();

        // Match the inbound result by its per-invocation call id.
        FunctionResultContent? matchingResult = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>()
            .FirstOrDefault(r => this.IsKnownPendingId(r.CallId));

        // Legacy non-approval backstop: when no pendings are tracked, accept a result
        // whose CallId equals this.Id. The runtime has already routed the response to
        // this executor's port and the framework does not invoke a function here.
        if (matchingResult is null
            && this._pendingNonApprovalCallIds.IsEmpty
            && this._approvalSnapshots.IsEmpty)
        {
            matchingResult = response.Messages
                .SelectMany(m => m.Contents)
                .OfType<FunctionResultContent>()
                .FirstOrDefault(r => string.Equals(r.CallId, this.Id, StringComparison.Ordinal));
        }

        // When the caller approved an approval-required function call but didn't execute it
        // locally (the hosted Foundry scenario, where mcp_approval_response is converted to a
        // ToolApprovalResponseContent only), invoke the registered AIFunction here so that the
        // declarative workflow can capture the result and continue (e.g. for downstream
        // SendActivity/PropertyPath consumers like {Local.Result}).
        if (matchingResult is null)
        {
            List<ToolApprovalResponseContent> approvals = response.Messages
                .SelectMany(m => m.Contents)
                .OfType<ToolApprovalResponseContent>()
                .ToList();

            // Prefer an approval matching a pending snapshot; otherwise take the first
            // present approval.
            ToolApprovalResponseContent? approval =
                approvals.FirstOrDefault(r => this._approvalSnapshots.ContainsKey(r.RequestId))
                ?? approvals.FirstOrDefault();

            if (approval is not null)
            {
                if (!this._approvalSnapshots.ContainsKey(approval.RequestId))
                {
                    await this.AssignErrorAsync(context, "No pending approval matched the response.").ConfigureAwait(false);
                }
                else if (!approval.Approved)
                {
                    this._approvalSnapshots.TryRemove(approval.RequestId, out _);
                    await this.AssignErrorAsync(context, "Function invocation was not approved by user.").ConfigureAwait(false);
                }
                else if (this._approvalSnapshots.TryRemove(approval.RequestId, out ApprovalSnapshot? snapshot))
                {
                    matchingResult = await this.InvokeRegisteredFunctionAsync(approval.RequestId, snapshot, cancellationToken).ConfigureAwait(false);
                }
                else
                {
                    await this.AssignErrorAsync(context, "No pending approval matched the response.").ConfigureAwait(false);
                }
            }
        }

        if (matchingResult is not null)
        {
            // Store the result in output variable
            await this.AssignResultAsync(context, matchingResult).ConfigureAwait(false);

            // Auto-send the result if configured
            if (autoSend)
            {
                AgentResponse resultResponse = new([new ChatMessage(ChatRole.Tool, [matchingResult])]);
                await context.AddEventAsync(new AgentResponseEvent(this.Id, resultResponse), cancellationToken).ConfigureAwait(false);
            }

            // Drop the per-invocation entry now that the response has been processed.
            this._pendingNonApprovalCallIds.TryRemove(matchingResult.CallId, out _);
            this._approvalSnapshots.TryRemove(matchingResult.CallId, out _);
        }

        // Store messages if output path is configured
        if (this.Model.Output?.Messages is not null)
        {
            await this.AssignAsync(this.Model.Output.Messages?.Path, response.Messages.ToFormula(), context).ConfigureAwait(false);
        }

        // Add messages to conversation if conversationId is provided
        // Note: We transform messages containing FunctionResultContent or FunctionCallContent
        // to assistant text messages because workflow-generated CallIds don't correspond to
        // actual AI-generated tool calls and would be rejected by the API.
        if (conversationId is not null)
        {
            foreach (ChatMessage message in TransformConversationMessages(response.Messages))
            {
                await agentProvider.CreateMessageAsync(conversationId, message, cancellationToken).ConfigureAwait(false);
            }
        }

        // Completes the action after processing the function result.
        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
    }

    private bool IsKnownPendingId(string callId) =>
        this._pendingNonApprovalCallIds.ContainsKey(callId) || this._approvalSnapshots.ContainsKey(callId);

    /// <inheritdoc/>
    public override ValueTask ResetAsync()
    {
        this._approvalSnapshots.Clear();
        this._pendingNonApprovalCallIds.Clear();
        return default;
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Persists pending approval snapshots and non-approval call ids so they survive
    /// checkpoint/restore cycles.
    /// </remarks>
    protected override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Dictionary<string, ApprovalSnapshot> snapshotCopy = this._approvalSnapshots.ToDictionary(kvp => kvp.Key, kvp => kvp.Value, StringComparer.Ordinal);
        await context.QueueStateUpdateAsync(ApprovalSnapshotStateKey, snapshotCopy, null, cancellationToken).ConfigureAwait(false);

        List<string> pendingCopy = [.. this._pendingNonApprovalCallIds.Keys];
        await context.QueueStateUpdateAsync(PendingCallIdsStateKey, pendingCopy, null, cancellationToken).ConfigureAwait(false);

        await base.OnCheckpointingAsync(context, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Restores pending approval snapshots and non-approval call ids from workflow state
    /// after a checkpoint restore.
    /// </remarks>
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);

        this._approvalSnapshots.Clear();
        Dictionary<string, ApprovalSnapshot>? snapshots = await context.ReadStateAsync<Dictionary<string, ApprovalSnapshot>>(
            ApprovalSnapshotStateKey, null, cancellationToken).ConfigureAwait(false);
        if (snapshots is not null)
        {
            foreach (KeyValuePair<string, ApprovalSnapshot> entry in snapshots)
            {
                this._approvalSnapshots[entry.Key] = entry.Value;
            }
        }

        this._pendingNonApprovalCallIds.Clear();
        List<string>? pending = await context.ReadStateAsync<List<string>>(
            PendingCallIdsStateKey, null, cancellationToken).ConfigureAwait(false);
        if (pending is not null)
        {
            foreach (string id in pending)
            {
                this._pendingNonApprovalCallIds.TryAdd(id, 0);
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

    /// <summary>
    /// Transforms messages containing function-related content to assistant text messages.
    /// Messages with FunctionResultContent are converted to assistant messages with the result as text.
    /// Messages with only FunctionCallContent are excluded as they have no informational value.
    /// </summary>
    private static IEnumerable<ChatMessage> TransformConversationMessages(IEnumerable<ChatMessage> messages)
    {
        foreach (ChatMessage message in messages)
        {
            // Check if message contains function content
            bool hasFunctionResult = message.Contents.OfType<FunctionResultContent>().Any();
            bool hasFunctionCall = message.Contents.OfType<FunctionCallContent>().Any();

            if (hasFunctionResult)
            {
                // Convert function results to assistant text message
                List<AIContent> updatedContents = [];
                foreach (AIContent content in message.Contents)
                {
                    if (content is FunctionResultContent functionResult)
                    {
                        string? resultText = functionResult.Result?.ToString();
                        if (!string.IsNullOrEmpty(resultText))
                        {
                            updatedContents.Add(new TextContent($"[Function {functionResult.CallId} result]: {resultText}"));
                        }
                    }
                    else if (content is not FunctionCallContent)
                    {
                        // Keep non-function content as-is
                        updatedContents.Add(content);
                    }
                }

                if (updatedContents.Count > 0)
                {
                    yield return new ChatMessage(ChatRole.Assistant, updatedContents);
                }
            }
            else if (!hasFunctionCall)
            {
                // Pass through messages without function content
                yield return message;
            }
        }
    }

    private async ValueTask AssignResultAsync(IWorkflowContext context, FunctionResultContent result)
    {
        if (this.Model.Output?.Result is null)
        {
            return;
        }

        object? resultValue = result.Result;

        // Attempt to parse as JSON if it's a string
        if (resultValue is string jsonString)
        {
            try
            {
                using JsonDocument jsonDocument = JsonDocument.Parse(jsonString);
                // Handle different JSON value kinds
                object? parsedValue = jsonDocument.RootElement.ValueKind switch
                {
                    JsonValueKind.Object => jsonDocument.ParseRecord(VariableType.RecordType),
                    JsonValueKind.Array => jsonDocument.ParseList(jsonDocument.RootElement.GetListTypeFromJson()),
                    JsonValueKind.String => jsonDocument.RootElement.GetString(),
                    JsonValueKind.Number => jsonDocument.RootElement.TryGetInt64(out long l) ? l : jsonDocument.RootElement.GetDouble(),
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    JsonValueKind.Null => null,
                    _ => jsonString,
                };
                await this.AssignAsync(this.Model.Output.Result?.Path, parsedValue.ToFormula(), context).ConfigureAwait(false);
                return;
            }
            catch (JsonException)
            {
                // Not a valid JSON
            }
        }

        await this.AssignAsync(this.Model.Output.Result?.Path, resultValue.ToFormula(), context).ConfigureAwait(false);
    }

    private async ValueTask AssignErrorAsync(IWorkflowContext context, string errorMessage)
    {
        if (this.Model.Output?.Result is not null)
        {
            await this.AssignAsync(this.Model.Output.Result?.Path, $"Error: {errorMessage}".ToFormula(), context).ConfigureAwait(false);
        }
    }

    private string GetFunctionName() =>
        this.Evaluator.GetValue(
            Throw.IfNull(
                this.Model.FunctionName,
                $"{nameof(this.Model)}.{nameof(this.Model.FunctionName)}")).Value;

    private string? GetConversationId()
    {
        if (this.Model.ConversationId is null)
        {
            return null;
        }

        string conversationIdValue = this.Evaluator.GetValue(this.Model.ConversationId).Value;
        return conversationIdValue.Length == 0 ? null : conversationIdValue;
    }

    private async ValueTask<FunctionResultContent?> InvokeRegisteredFunctionAsync(string callId, ApprovalSnapshot snapshot, CancellationToken cancellationToken)
    {
        // Use the snapshot captured at approval-request time so we invoke exactly what
        // the user approved, even if Power Fx state has mutated during the approval window.
        string functionName = snapshot.FunctionName;
        Dictionary<string, object?>? arguments = snapshot.Arguments;

        AIFunction? function = agentProvider.Functions?.FirstOrDefault(
            f => string.Equals(f.Name, functionName, StringComparison.Ordinal));

        if (function is null)
        {
            return new FunctionResultContent(callId, result: null)
            {
                Exception = new InvalidOperationException(
                    $"Function '{functionName}' is not registered with the agent provider."),
            };
        }

        AIFunctionArguments? functionArguments = arguments is null ? null : new AIFunctionArguments(arguments.NormalizePortableValues());

        object? result;
        try
        {
            result = await function.InvokeAsync(functionArguments, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            return new FunctionResultContent(callId, result: null) { Exception = ex };
        }

        // Match FunctionInvokingChatClient's serialization: pass strings through as-is and
        // JSON-serialize anything else so structured results remain consumable by downstream
        // PropertyPath consumers such as {Local.RefundResult}. Use AIJsonUtilities so the
        // same trim/AOT-friendly serializer chain used elsewhere in the framework is applied.
        string serialized = result switch
        {
            null => string.Empty,
            string s => s,
            _ => JsonSerializer.Serialize(result, AIJsonUtilities.DefaultOptions.GetTypeInfo(result.GetType())),
        };

        return new FunctionResultContent(callId, serialized);
    }

    private bool GetRequireApproval()
    {
        if (this.Model.RequireApproval is null)
        {
            return false;
        }

        return this.Evaluator.GetValue(this.Model.RequireApproval).Value;
    }

    private bool GetAutoSendValue()
    {
        // InvokeToolOutput.AutoSend is never null — it returns a literal-false default
        // when the YAML omits the field. Use AutoSendIsDefaultValue to distinguish an
        // explicit autoSend value from the implicit default, and treat the implicit
        // default as autoSend = true (the historical behavior).
        if (this.Model.Output is { AutoSendIsDefaultValue: false } output)
        {
            return this.Evaluator.GetValue(output.AutoSend).Value;
        }

        return true;
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
            result[argument.Key] = this.Evaluator.GetValue(argument.Value).Value.ToObject();
        }

        return result;
    }

    /// <summary>
    /// Captured invocation parameters used by <see cref="CaptureResponseAsync"/> on
    /// resume so the approved values are invoked regardless of subsequent state changes.
    /// </summary>
    internal sealed record ApprovalSnapshot(
        string FunctionName,
        Dictionary<string, object?>? Arguments);
}
