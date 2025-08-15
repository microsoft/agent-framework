// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class AnswerQuestionWithAIExecutor(AnswerQuestionWithAI model) : WorkflowActionExecutor<AnswerQuestionWithAI>(model)
{
    protected override async ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(this.Model.Variable)}");
        StringExpression userInputExpression = Throw.IfNull(this.Model.UserInput, $"{nameof(this.Model)}.{nameof(this.Model.UserInput)}");

        PersistentAgentsClient client = this.Context.ClientFactory.Invoke();
        using NewPersistentAgentsChatClient chatClient = new(client, "asst_ueIjfGxAjsnZ4A61LlbjG9vJ"); // %%% HAXX - AGENT ID
        ChatClientAgent agent = new(chatClient);

        string? userInput = null;
        if (this.Model.UserInput is not null)
        {
            EvaluationResult<string> result = this.Context.ExpressionEngine.GetValue(userInputExpression, this.Context.Scopes);
            userInput = result.Value;
        }

        ChatClientAgentRunOptions options =
            new(
                new ChatOptions()
                {
                    Instructions = this.Context.Engine.Format(this.Model.AdditionalInstructions) ?? string.Empty,
                });

        //AgentRunResponse agentResponse =
        //    userInput != null ?
        //        await agent.RunAsync(userInput, thread: null, options, cancellationToken).ConfigureAwait(false) :
        //        await agent.RunAsync(thread: null, options, cancellationToken).ConfigureAwait(false);

        IAsyncEnumerable<AgentRunResponseUpdate> agentUpdates =
            userInput != null ?
                agent.RunStreamingAsync(userInput, thread: null, options, cancellationToken) :
                agent.RunStreamingAsync(thread: null, options, cancellationToken);

        await context.AddEventAsync(new DeclarativeWorkflowMessageEvent(new ChatMessage(ChatRole.Assistant, "TESTING"))).ConfigureAwait(false);

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
            conversationId ??= update.ResponseId;
            messageId ??= update.MessageId;
            await context.AddEventAsync(new DeclarativeWorkflowStreamEvent(update)).ConfigureAwait(false);
        }

        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("STREAM: COMPLETE");
        Console.ResetColor();

        AgentRunResponse agentResponse = agentResponseUpdates.ToAgentRunResponse();

        ChatMessage response = agentResponse.Messages.Last(); // %%% DECISION: Is last sufficient? (probably not)
        await context.AddEventAsync(new DeclarativeWorkflowMessageEvent(response, agentResponse.Usage)).ConfigureAwait(false);

        this.AssignTarget(this.Context, variablePath, response.ToRecord());
    }
}
