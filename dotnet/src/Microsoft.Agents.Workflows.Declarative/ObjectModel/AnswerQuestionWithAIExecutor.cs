// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
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

internal sealed class AnswerQuestionWithAIExecutor(AnswerQuestionWithAI model, PersistentAgentsClient client) : DeclarativeActionExecutor<AnswerQuestionWithAI>(model)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        StringExpression userInputExpression = Throw.IfNull(this.Model.UserInput, $"{nameof(this.Model)}.{nameof(this.Model.UserInput)}");

        using NewPersistentAgentsChatClient chatClient = new(client, this.Id); // %%% HAXX - AGENT ID
        ChatClientAgent agent = new(chatClient);

        string? userInput = null;
        if (this.Model.UserInput is not null)
        {
            EvaluationResult<string> expressionResult = this.State.ExpressionEngine.GetValue(userInputExpression, this.State.Scopes);
            userInput = expressionResult.Value;
        }

        ChatClientAgentRunOptions options =
            new(
                new ChatOptions()
                {
                    Instructions = this.State.Format(this.Model.AdditionalInstructions) ?? string.Empty,
                });

        //AgentRunResponse agentResponse =
        //    userInput != null ?
        //        await agent.RunAsync(userInput, thread: null, options, cancellationToken).ConfigureAwait(false) :
        //        await agent.RunAsync(thread: null, options, cancellationToken).ConfigureAwait(false);

        AgentThread? thread = null; // %%% HAXX: SYSTEM THREAD
        FormulaValue conversationValue = this.State.Scopes.Get("ConversationId", WorkflowScopeType.System);
        if (conversationValue is StringValue stringValue)
        {
            thread = new AgentThread() { ConversationId = stringValue.Value };
        }

        IAsyncEnumerable<AgentRunResponseUpdate> agentUpdates =
            !string.IsNullOrWhiteSpace(userInput) ?
                agent.RunStreamingAsync(userInput, thread, options, cancellationToken) :
                agent.RunStreamingAsync(thread, options, cancellationToken);

        string? conversationId = null;
        string? messageId = null;
        List<AgentRunResponseUpdate> agentResponseUpdates = [];
        await foreach (AgentRunResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            if (messageId is null)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("STREAM: BEGIN");
                Console.ResetColor();
            }

            agentResponseUpdates.Add(update);
            conversationId ??= ((ChatResponseUpdate)update.RawRepresentation!).ConversationId;
            messageId ??= update.MessageId;
            await context.AddEventAsync(new DeclarativeWorkflowStreamEvent(update)).ConfigureAwait(false);
        }

        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("STREAM: COMPLETE");
        Console.ResetColor();

        AgentRunResponse agentResponse = agentResponseUpdates.ToAgentRunResponse();

        ChatMessage response = agentResponse.Messages.Last(); // %%% DECISION: Is last sufficient? (probably not)
        await context.AddEventAsync(new DeclarativeWorkflowMessageEvent(response, agentResponse.Usage)).ConfigureAwait(false);

        this.AssignTarget(PropertyPath.FromSegments(WorkflowScopeType.System.Name, "ConversationId"), FormulaValue.New(conversationId)); // %%% HAXX: SYSTEM THREAD

        PropertyPath? variablePath = this.Model.Variable?.Path;
        if (variablePath is not null)
        {
            this.AssignTarget(variablePath, response.ToRecordValue());
        }

        return default;
    }
}
