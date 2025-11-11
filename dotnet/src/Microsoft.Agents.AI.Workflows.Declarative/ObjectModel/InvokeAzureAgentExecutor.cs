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
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class InvokeAzureAgentExecutor(InvokeAzureAgent model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<InvokeAzureAgent>(model, state)
{
    public static class Steps
    {
        public static string ExternalInput(string id) => $"{id}_{nameof(ExternalInput)}";
        public static string Resume(string id) => $"{id}_{nameof(Resume)}";
    }

    public static bool RequiresInput(object? message) => message is ExternalInputRequest;

    public static bool RequiresNothing(object? message) => message is ActionExecutorResult;

    private AzureAgentUsage AgentUsage => Throw.IfNull(this.Model.Agent, $"{nameof(this.Model)}.{nameof(this.Model.Agent)}");
    private AzureAgentInput? AgentInput => this.Model.Input;
    private AzureAgentOutput? AgentOutput => this.Model.Output;

    protected override bool EmitResultEvent => false;
    protected override bool IsDiscreteAction => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await this.InvokeAgentAsync(context, this.GetInputMessages(), cancellationToken).ConfigureAwait(false);

        return default;
    }

    public async ValueTask ResumeAsync(IWorkflowContext context, ExternalInputResponse response, CancellationToken cancellationToken)
    {
        await context.SetLastMessageAsync(response.Messages.Last()).ConfigureAwait(false);
        await this.InvokeAgentAsync(context, response.Messages, cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask CompleteAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
    {
        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask InvokeAgentAsync(IWorkflowContext context, IEnumerable<ChatMessage>? messages, CancellationToken cancellationToken)
    {
        string? conversationId = this.GetConversationId();
        string agentName = this.GetAgentName();
        bool autoSend = this.GetAutoSendValue();
        Dictionary<string, object?>? inputParameters = this.GetStructuredInputs();
        AgentRunResponse agentResponse = await agentProvider.InvokeAgentAsync(this.Id, context, agentName, conversationId, autoSend, messages, inputParameters, cancellationToken).ConfigureAwait(false);

        ChatMessage[] actionableMessages = FilterActionableContent(agentResponse).ToArray();
        if (actionableMessages.Length > 0)
        {
            AgentRunResponse filteredResponse =
                new(actionableMessages)
                {
                    AdditionalProperties = agentResponse.AdditionalProperties,
                    AgentId = agentResponse.AgentId,
                    CreatedAt = agentResponse.CreatedAt,
                    ResponseId = agentResponse.ResponseId,
                    Usage = agentResponse.Usage,
                };
            await context.SendMessageAsync(new ExternalInputRequest(filteredResponse), cancellationToken).ConfigureAwait(false);
            return;
        }

        await this.AssignAsync(this.AgentOutput?.Messages?.Path, agentResponse.Messages.ToTable(), context).ConfigureAwait(false);

        // Attempt to parse the last message as JSON and assign to the response object variable.
        try
        {
            JsonDocument jsonDocument = JsonDocument.Parse(agentResponse.Messages.Last().Text);
            Dictionary<string, object?> objectProperties = jsonDocument.ParseRecord(VariableType.RecordType);
            await this.AssignAsync(this.AgentOutput?.ResponseObject?.Path, objectProperties.ToFormula(), context).ConfigureAwait(false);
        }
        catch
        {
            // Not valid json, skip assignment.
        }

        if (this.Model.Input?.ExternalLoop?.When is not null)
        {
            bool requestInput = this.Evaluator.GetValue(this.Model.Input.ExternalLoop.When).Value;
            if (requestInput)
            {
                ExternalInputRequest inputRequest = new(agentResponse);
                await context.SendMessageAsync(inputRequest, cancellationToken).ConfigureAwait(false);
                return;
            }
        }

        await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
    }

    private Dictionary<string, object?>? GetStructuredInputs()
    {
        Dictionary<string, object?>? inputs = null;

        if (this.AgentInput?.Arguments is not null)
        {
            inputs = [];

            foreach (KeyValuePair<string, ValueExpression> argument in this.AgentInput.Arguments)
            {
                inputs[argument.Key] = this.Evaluator.GetValue(argument.Value).Value.ToObject();
            }
        }

        return inputs;
    }

    private IEnumerable<ChatMessage>? GetInputMessages()
    {
        DataValue? userInput = null;

        if (this.AgentInput?.Messages is not null)
        {
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.AgentInput.Messages);
            userInput = expressionResult.Value;
        }

        return userInput?.ToChatMessages();
    }

    private static IEnumerable<ChatMessage> FilterActionableContent(AgentRunResponse agentResponse)
    {
        HashSet<string> functionResultIds =
            [.. agentResponse.Messages
                    .SelectMany(
                        m =>
                            m.Contents
                                .OfType<FunctionResultContent>()
                                .Select(functionCall => functionCall.CallId))];

        foreach (ChatMessage responseMessage in agentResponse.Messages)
        {
            if (responseMessage.Contents.Any(content => content is UserInputRequestContent))
            {
                yield return responseMessage;
                continue;
            }

            if (responseMessage.Contents.OfType<FunctionCallContent>().Any(functionCall => !functionResultIds.Contains(functionCall.CallId)))
            {
                yield return responseMessage;
            }
        }
    }

    private string? GetConversationId()
    {
        if (this.Model.ConversationId is null)
        {
            return null;
        }

        EvaluationResult<string> conversationIdResult = this.Evaluator.GetValue(this.Model.ConversationId);
        return conversationIdResult.Value.Length == 0 ? null : conversationIdResult.Value;
    }

    private string GetAgentName() =>
        this.Evaluator.GetValue(
            Throw.IfNull(
                this.AgentUsage.Name,
                $"{nameof(this.Model)}.{nameof(this.Model.Agent)}.{nameof(this.Model.Agent.Name)}")).Value;

    private bool GetAutoSendValue()
    {
        if (this.AgentOutput?.AutoSend is null)
        {
            return true;
        }

        EvaluationResult<bool> autoSendResult = this.Evaluator.GetValue(this.AgentOutput.AutoSend);

        return autoSendResult.Value;
    }
}
