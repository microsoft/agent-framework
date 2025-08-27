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

internal sealed class AnswerQuestionWithAIExecutor(AnswerQuestionWithAI model, WorkflowAgentProvider agentProvider) : DeclarativeActionExecutor<AnswerQuestionWithAI>(model)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        StringExpression userInputExpression = Throw.IfNull(this.Model.UserInput, $"{nameof(this.Model)}.{nameof(this.Model.UserInput)}");

        string agentInstructions = this.State.Format(this.Model.AdditionalInstructions) ?? string.Empty;
        // ISSUE #485 - Agent identifier embedded in instructions until updated OM is available.
        string agentId;
        string? additionalInstructions = null;
        int delimiterIndex = agentInstructions.IndexOf(',');
        if (delimiterIndex < 0)
        {
            agentId = agentInstructions.Trim();
        }
        else
        {
            agentId = agentInstructions.Substring(0, delimiterIndex).Trim();
            additionalInstructions = agentInstructions.Substring(delimiterIndex + 1).Trim();
        }

        AIAgent agent = await agentProvider.GetAgentAsync(agentId, cancellationToken).ConfigureAwait(false);

        string? userInput = null;
        if (this.Model.UserInput is not null)
        {
            EvaluationResult<string> expressionResult = this.State.ExpressionEngine.GetValue(userInputExpression);
            userInput = expressionResult.Value;
        }

        ChatClientAgentRunOptions options =
            new(
                new ChatOptions()
                {
                    Instructions = additionalInstructions,
                });

        FormulaValue conversationValue =
            this.Model.AutoSend ? // ISSUE #485: Conversation implicitly managed until updated OM is available.
                this.State.GetConversationId() :
                this.State.GetInternalConversationId();

        string? conversationId = null;
        if (conversationValue is StringValue stringValue)
        {
            await AssignConversationId(stringValue.Value).ConfigureAwait(false);
        }

        AgentThread agentThread = new() { ConversationId = conversationId };
        IAsyncEnumerable<AgentRunResponseUpdate> agentUpdates =
                !string.IsNullOrWhiteSpace(userInput) ?
                    agent.RunStreamingAsync(userInput, agentThread, options, cancellationToken) :
                    agent.RunStreamingAsync(agentThread, options, cancellationToken);

        string? messageId = null;
        List<AgentRunResponseUpdate> agentResponseUpdates = new(0x400);
        await foreach (AgentRunResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            agentResponseUpdates.Add(update);
            messageId ??= update.MessageId;
            await AssignConversationId(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);
            if (this.Model.AutoSend)
            {
                await context.AddEventAsync(new DeclarativeWorkflowStreamEvent(update)).ConfigureAwait(false);
            }
        }

        AgentRunResponse agentResponse = agentResponseUpdates.ToAgentRunResponse();

        ChatMessage response = agentResponse.Messages.Last();
        this.State.SetLastMessage(response);
        if (this.Model.AutoSend)
        {
            await context.AddEventAsync(new DeclarativeWorkflowMessageEvent(response, agentResponse.Usage)).ConfigureAwait(false);
        }

        // Assign conversation ID if it wasn't already assigned.
        if (conversationValue is not StringValue && conversationId is not null)
        {
            if (this.Model.AutoSend) // ISSUE #485: Conversation implicitly managed until updated OM is available.
            {
                this.State.SetConversationId(conversationId);
            }
            else
            {
                this.State.SetInternalConversationId(conversationId);
            }
        }

        PropertyPath? variablePath = this.Model.Variable?.Path;
        if (variablePath is not null)
        {
            this.AssignTarget(variablePath, response.ToRecord());
        }

        return default;

        async ValueTask AssignConversationId(string? assignValue)
        {
            if (assignValue != null && conversationId == null)
            {
                conversationId = assignValue;
                await context.AddEventAsync(new DeclarativeWorkflowInvokeEvent(conversationId)).ConfigureAwait(false);
            }
        }
    }
}
