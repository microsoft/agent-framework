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
/// Executor for the <see cref="InvokeFunctionTool"/> action.
/// This executor yields to the caller for function execution and resumes when results are provided.
/// </summary>
internal sealed class InvokeFunctionToolExecutor(
    InvokeFunctionTool model,
    ResponseAgentProvider agentProvider,
    WorkflowFormulaState state) :
    DeclarativeActionExecutor<InvokeFunctionTool>(model, state)
{
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
            requestMessage.Contents.Add(new FunctionApprovalRequestContent(this.Id, functionCall));
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
}
