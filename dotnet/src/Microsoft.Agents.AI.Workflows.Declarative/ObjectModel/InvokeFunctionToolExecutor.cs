// Copyright (c) Microsoft. All rights reserved.

using System;
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
using Microsoft.Extensions.Logging;
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
    private const string ApprovalSnapshotStateKey = nameof(_approvalSnapshot);

    /// <summary>
    /// Snapshot of evaluated parameters at approval-request time.
    /// </summary>
    private ApprovalSnapshot? _approvalSnapshot;

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

        // Create the function call content to send to the caller
        FunctionCallContent functionCall = new(
            callId: this.Id,
            name: functionName,
            arguments: arguments);

        // Build the response with the function call request
        ChatMessage requestMessage = new(ChatRole.Tool, [functionCall]);

        // If approval is required, add user input request content
        if (requireApproval)
        {
            // Snapshot the evaluated parameters.
            // If state mutates during the approval window, the approved values are used on resume.
            this._approvalSnapshot = new ApprovalSnapshot(functionName, arguments);

            requestMessage.Contents.Add(new ToolApprovalRequestContent(this.Id, functionCall));
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

        // Extract function results from the response
        IEnumerable<FunctionResultContent> functionResults = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>();

        FunctionResultContent? matchingResult = functionResults
            .FirstOrDefault(r => r.CallId == this.Id);

        // When the caller approved an approval-required function call but didn't execute it
        // locally (the hosted Foundry scenario, where mcp_approval_response is converted to a
        // ToolApprovalResponseContent only), invoke the registered AIFunction here so that the
        // declarative workflow can capture the result and continue (e.g. for downstream
        // SendActivity/PropertyPath consumers like {Local.Result}).
        if (matchingResult is null)
        {
            ToolApprovalResponseContent? approval = response.Messages
                .SelectMany(m => m.Contents)
                .OfType<ToolApprovalResponseContent>()
                .FirstOrDefault(r => r.RequestId == this.Id);

            if (approval is { Approved: true })
            {
                matchingResult = await this.InvokeRegisteredFunctionAsync(cancellationToken).ConfigureAwait(false);
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

        // Clear the approval snapshot after the action completes so a subsequent
        // execution of the same executor instance doesn't reuse stale data.
        this._approvalSnapshot = null;
        await context.QueueStateUpdateAsync<ApprovalSnapshot?>(ApprovalSnapshotStateKey, null, null, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Persists the approval snapshot to workflow state so it survives checkpoint/restore cycles.
    /// </remarks>
    protected override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await context.QueueStateUpdateAsync(ApprovalSnapshotStateKey, this._approvalSnapshot, null, cancellationToken).ConfigureAwait(false);
        await base.OnCheckpointingAsync(context, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Restores the approval snapshot from workflow state after a checkpoint restore.
    /// </remarks>
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);
        this._approvalSnapshot = await context.ReadStateAsync<ApprovalSnapshot>(ApprovalSnapshotStateKey, null, cancellationToken).ConfigureAwait(false);
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

    private async ValueTask<FunctionResultContent?> InvokeRegisteredFunctionAsync(CancellationToken cancellationToken)
    {
        string functionName;
        Dictionary<string, object?>? arguments;

        if (this._approvalSnapshot is { } snapshot)
        {
            // Use the snapshot captured at approval-request time so we invoke exactly what
            // the user approved, even if Power Fx state has mutated during the approval window.
            functionName = snapshot.FunctionName;
            arguments = snapshot.Arguments;
        }
        else
        {
            // Fallback for checkpoints created before approval snapshots were introduced.
            this.Logger.LogWarning("Approval snapshot missing for '{ActionId}'; falling back to expression re-evaluation.", this.Id);
            functionName = this.GetFunctionName();
            arguments = this.GetArguments();
        }

        AIFunction? function = agentProvider.Functions?.FirstOrDefault(
            f => string.Equals(f.Name, functionName, StringComparison.Ordinal));

        if (function is null)
        {
            return new FunctionResultContent(this.Id, result: null)
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
            return new FunctionResultContent(this.Id, result: null) { Exception = ex };
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

        return new FunctionResultContent(this.Id, serialized);
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
    /// Stores the evaluated parameters at approval-request time so that
    /// <see cref="CaptureResponseAsync"/> uses the values the user reviewed,
    /// even if <see cref="WorkflowFormulaState"/> mutates during the approval window.
    /// </summary>
    internal sealed record ApprovalSnapshot(
        string FunctionName,
        Dictionary<string, object?>? Arguments);
}
