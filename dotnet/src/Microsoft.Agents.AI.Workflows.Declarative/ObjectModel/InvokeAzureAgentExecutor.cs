// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.IO;
using System.Linq;
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
using static Microsoft.Agents.AI.Workflows.Declarative.PowerFx.TypeSchema;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class InvokeAzureAgentExecutor(InvokeAzureAgent model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<InvokeAzureAgent>(model, state)
{
    public static class Steps
    {
        public static string Input(string id) => $"{id}_{nameof(Input)}";
        public static string Resume(string id) => $"{id}_{nameof(Resume)}";
    }

    // Input is requested by a message other than ActionExecutorResult.
    public static bool RequiresInput(object? message) => message is not ActionExecutorResult;

    private AzureAgentUsage AgentUsage => Throw.IfNull(this.Model.Agent, $"{nameof(this.Model)}.{nameof(this.Model.Agent)}");
    private AzureAgentInput? AgentInput => this.Model.Input;
    private AzureAgentOutput? AgentOutput => this.Model.Output;

    protected override bool EmitResultEvent => false;
    protected override bool IsDiscreteAction => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string? conversationId = this.GetConversationId();
        string agentName = this.GetAgentName();
        string? additionalInstructions = this.GetAdditionalInstructions();
        bool autoSend = this.GetAutoSendValue();
        IEnumerable<ChatMessage>? inputMessages = this.GetInputMessages();

        AgentRunResponse agentResponse = await agentProvider.InvokeAgentAsync(this.Id, context, agentName, conversationId, autoSend, additionalInstructions, inputMessages, cancellationToken).ConfigureAwait(false);

        bool isComplete = true;
        if (string.IsNullOrEmpty(agentResponse.Text))
        {
            Dictionary<string, FunctionCallContent> toolCalls = agentResponse.Messages.SelectMany(m => m.Contents.OfType<FunctionCallContent>()).ToDictionary(tool => tool.CallId);
            HashSet<string> pendingToolCalls = toolCalls.Keys.Except(agentResponse.Messages.SelectMany(m => m.Contents.OfType<FunctionResultContent>()).Select(tool => tool.CallId)).ToHashSet();
            if (pendingToolCalls.Count > 0)
            {
                AgentToolRequest toolRequest =
                    new(agentName,
                        toolCalls
                            .Where(toolCall => pendingToolCalls.Contains(toolCall.Value.CallId))
                            .Select(toolCall => toolCall.Value));
                await context.SendMessageAsync(toolRequest, targetId: null, cancellationToken).ConfigureAwait(false);
                isComplete = false;
            }
        }

        if (isComplete)
        {
            await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
        }

        await this.AssignAsync(this.AgentOutput?.Messages?.Path, agentResponse.Messages.ToTable(), context).ConfigureAwait(false);

        return default;
    }

    public async ValueTask ResumeAsync(IWorkflowContext context, AgentToolResponse message, CancellationToken cancellationToken)
    {
        string? conversationId = this.GetConversationId();
        string agentName = this.GetAgentName();
        string? additionalInstructions = this.GetAdditionalInstructions();
        bool autoSend = this.GetAutoSendValue();
        ChatMessage resultMessage = new(ChatRole.Tool, [.. message.FunctionResults]);

        //await agentProvider.CreateMessageAsync(conversationId!, resultMessage, cancellationToken).ConfigureAwait(false); // %%% HAXX

        // %%% TOOL: CONVERGE
        AgentRunResponse agentResponse = await agentProvider.InvokeAgentAsync(this.Id, context, agentName, conversationId, autoSend, additionalInstructions, [resultMessage], cancellationToken).ConfigureAwait(false);

        await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);

        await this.AssignAsync(this.AgentOutput?.Messages?.Path, agentResponse.Messages.ToTable(), context).ConfigureAwait(false);
    }

    public async ValueTask CompleteAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
    {
        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
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

    private string? GetAdditionalInstructions()
    {
        string? additionalInstructions = null;

        if (this.AgentInput?.AdditionalInstructions is not null)
        {
            additionalInstructions = this.Engine.Format(this.AgentInput.AdditionalInstructions);
        }

        return additionalInstructions;
    }

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
