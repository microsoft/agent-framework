// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class InvokeAzureAgentExecutor(InvokeAzureAgent model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<InvokeAzureAgent>(model, state)
{
    private AzureAgentUsage AgentUsage => Throw.IfNull(this.Model.Agent, $"{nameof(this.Model)}.{nameof(this.Model.Agent)}");
    private AzureAgentInput? AgentInput => this.Model.Input;
    private AzureAgentOutput? AgentOutput => this.Model.Output;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        string? conversationId = this.GetConversationId();
        string agentName = this.GetAgentName();
        string? additionalInstructions = this.GetAdditionalInstructions();
        bool autoSend = this.GetAutoSendValue();
        DataValue? inputMessages = this.GetInputMessages();

        AgentRunResponse agentResponse = InvokeAgentAsync().ToEnumerable().ToAgentRunResponse();

        if (autoSend)
        {
            await context.AddEventAsync(new AgentRunResponseEvent(this.Id, agentResponse)).ConfigureAwait(false);
        }

        ChatMessage response = agentResponse.Messages[agentResponse.Messages.Count - 1];
        await this.AssignAsync(this.AgentOutput?.Messages?.Path, response.ToRecord(), context).ConfigureAwait(false);

        return default;

        async IAsyncEnumerable<AgentRunResponseUpdate> InvokeAgentAsync()
        {
            AIAgent agent = await agentProvider.GetAgentAsync(agentName, cancellationToken).ConfigureAwait(false);

            ChatClientAgentRunOptions options =
                new(
                    new ChatOptions()
                    {
                        Instructions = additionalInstructions,
                    });

            AgentThread agentThread = conversationId is not null && agent is ChatClientAgent chatClientAgent ? chatClientAgent.GetNewThread(conversationId) : agent.GetNewThread();
            IAsyncEnumerable<AgentRunResponseUpdate> agentUpdates =
                inputMessages is not null ?
                    agent.RunStreamingAsync([.. inputMessages.ToChatMessages()], agentThread, options, cancellationToken) :
                    agent.RunStreamingAsync(agentThread, options, cancellationToken);

            await foreach (AgentRunResponseUpdate update in agentUpdates.ConfigureAwait(false))
            {
                await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);

                if (autoSend)
                {
                    await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update)).ConfigureAwait(false);
                }

                yield return update;
            }
        }

        async ValueTask AssignConversationIdAsync(string? assignValue)
        {
            if (assignValue is not null && conversationId is null)
            {
                conversationId = assignValue;

                RecordValue conversation = (RecordValue)context.ReadState(SystemScope.Names.Conversation, VariableScopeNames.System);
                conversation.UpdateField("Id", FormulaValue.New(conversationId));
                await context.QueueSystemUpdateAsync(SystemScope.Names.Conversation, conversation).ConfigureAwait(false);
                await context.QueueSystemUpdateAsync(SystemScope.Names.ConversationId, FormulaValue.New(conversationId)).ConfigureAwait(false);

                await context.AddEventAsync(new ConversationUpdateEvent(conversationId)).ConfigureAwait(false);
            }
        }
    }

    private DataValue? GetInputMessages()
    {
        DataValue? userInput = null;
        if (this.AgentInput?.Messages is not null)
        {
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.AgentInput.Messages);
            userInput = expressionResult.Value;
        }

        return userInput;
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
