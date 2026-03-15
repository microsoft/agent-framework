// Copyright (c) Microsoft. All rights reserved.

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
    public static bool RequiresInput(object? message) => message is ExternalInputRequest;

    /// <summary>
    /// Determines if the message indicates no external input is required.
    /// </summary>
    public static bool RequiresNothing(object? message) => message is ActionExecutorResult;

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
        Dictionary<string, object?>? arguments = this.GetArguments();
        Dictionary<string, string>? headers = this.GetHeaders();
        string? connectionName = this.GetConnectionName();

        if (requireApproval)
        {
            // Create tool call content for approval request
            McpServerToolCallContent toolCall = new(this.Id, toolName, serverLabel ?? serverUrl)
            {
                Arguments = arguments
            };

            if (headers != null)
            {
                toolCall.AdditionalProperties ??= [];
                toolCall.AdditionalProperties.Add(headers);
            }

            McpServerToolApprovalRequestContent approvalRequest = new(this.Id, toolCall);

            ChatMessage requestMessage = new(ChatRole.Assistant, [approvalRequest]);
            AgentResponse agentResponse = new([requestMessage]);

            // Yield to the caller for approval
            ExternalInputRequest inputRequest = new(agentResponse);
            await context.SendMessageAsync(inputRequest, cancellationToken).ConfigureAwait(false);

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

        await this.ProcessResultAsync(context, resultContent, cancellationToken).ConfigureAwait(false);

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
    public async ValueTask CaptureResponseAsync(
        IWorkflowContext context,
        ExternalInputResponse response,
        CancellationToken cancellationToken)
    {
        // Check for approval response
        McpServerToolApprovalResponseContent? approvalResponse = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<McpServerToolApprovalResponseContent>()
            .FirstOrDefault(r => r.Id == this.Id);

        if (approvalResponse?.Approved != true)
        {
            // Tool call was rejected
            await this.AssignErrorAsync(context, "MCP tool invocation was not approved by user.").ConfigureAwait(false);
            return;
        }

        // Approved - now invoke the tool
        string serverUrl = this.GetServerUrl();
        string? serverLabel = this.GetServerLabel();
        string toolName = this.GetToolName();
        Dictionary<string, object?>? arguments = this.GetArguments();
        Dictionary<string, string>? headers = this.GetHeaders();
        string? connectionName = this.GetConnectionName();

        McpServerToolResultContent resultContent = await mcpToolHandler.InvokeToolAsync(
            serverUrl,
            serverLabel,
            toolName,
            arguments,
            headers,
            connectionName,
            cancellationToken).ConfigureAwait(false);

        await this.ProcessResultAsync(context, resultContent, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Completes the MCP tool invocation by raising the completion event.
    /// </summary>
    public async ValueTask CompleteAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
    {
        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask ProcessResultAsync(IWorkflowContext context, McpServerToolResultContent resultContent, CancellationToken cancellationToken)
    {
        bool autoSend = this.GetAutoSendValue();
        string? conversationId = this.GetConversationId();

        await this.AssignResultAsync(context, resultContent).ConfigureAwait(false);
        ChatMessage resultMessage = new(ChatRole.Tool, resultContent.Output);

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
            ChatMessage assistantMessage = new(ChatRole.Assistant, resultContent.Output);
            await agentProvider.CreateMessageAsync(conversationId, assistantMessage, cancellationToken).ConfigureAwait(false);
        }
    }

    private async ValueTask AssignResultAsync(IWorkflowContext context, McpServerToolResultContent toolResult)
    {
        if (this.Model.Output?.Result is null || toolResult.Output is null || toolResult.Output.Count == 0)
        {
            return;
        }

        List<object?> parsedResults = [];
        foreach (AIContent resultContent in toolResult.Output)
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
        this.Evaluator.GetValue(
            Throw.IfNull(
                this.Model.ServerUrl,
                $"{nameof(this.Model)}.{nameof(this.Model.ServerUrl)}")).Value;

    private string? GetServerLabel()
    {
        if (this.Model.ServerLabel is null)
        {
            return null;
        }

        string value = this.Evaluator.GetValue(this.Model.ServerLabel).Value;
        return value.Length == 0 ? null : value;
    }

    private string GetToolName() =>
        this.Evaluator.GetValue(
            Throw.IfNull(
                this.Model.ToolName,
                $"{nameof(this.Model)}.{nameof(this.Model.ToolName)}")).Value;

    private string? GetConversationId()
    {
        if (this.Model.ConversationId is null)
        {
            return null;
        }

        string value = this.Evaluator.GetValue(this.Model.ConversationId).Value;
        return value.Length == 0 ? null : value;
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
        if (this.Model.Output?.AutoSend is null)
        {
            return true;
        }

        return this.Evaluator.GetValue(this.Model.Output.AutoSend).Value;
    }

    private string? GetConnectionName()
    {
        if (this.Model.Connection?.Name is null)
        {
            return null;
        }

        string value = this.Evaluator.GetValue(this.Model.Connection.Name).Value;
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
            result[argument.Key] = this.Evaluator.GetValue(argument.Value).Value.ToObject();
        }

        return result;
    }

    private Dictionary<string, string>? GetHeaders()
    {
        if (this.Model.Headers is null)
        {
            return null;
        }

        Dictionary<string, string> result = [];
        foreach (KeyValuePair<string, StringExpression> header in this.Model.Headers)
        {
            string value = this.Evaluator.GetValue(header.Value).Value;
            if (!string.IsNullOrEmpty(value))
            {
                result[header.Key] = value;
            }
        }

        return result;
    }
}
