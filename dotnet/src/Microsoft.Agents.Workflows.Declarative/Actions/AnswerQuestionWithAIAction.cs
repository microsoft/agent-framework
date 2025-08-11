// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Microsoft.Agents.Workflows.Declarative;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Handlers;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.SemanticKernel.Process.Workflows.Actions;

internal sealed class AnswerQuestionWithAIAction : AssignmentAction<AnswerQuestionWithAI>
{
    public AnswerQuestionWithAIAction(AnswerQuestionWithAI model)
        : base(model, Throw.IfNull(model.Variable?.Path, $"{nameof(model)}.{nameof(model.Variable)}.{nameof(InitializablePropertyPath.Path)}"))
    {
    }

    protected override async Task HandleAsync(ProcessActionContext context, CancellationToken cancellationToken)
    {
        PersistentAgentsClient client = context.ClientFactory.Invoke();
        using NewPersistentAgentsChatClient chatClient = new(client, "asst_ueIjfGxAjsnZ4A61LlbjG9vJ");
        ChatClientAgent agent = new(chatClient);

        string? userInput = null;
        if (this.Model.UserInput is not null)
        {
            EvaluationResult<string> result = context.ExpressionEngine.GetValue(this.Model.UserInput!, context.Scopes); // %%% FAILURE CASE (CATCH) & NULL OVERRIDE
            userInput = result.Value;
        }

        ChatClientAgentRunOptions options =
            new(
                new ChatOptions()
                {
                    Instructions = context.Engine.Format(this.Model.AdditionalInstructions) ?? string.Empty,
                });
        AgentRunResponse response =
            userInput != null ?
                await agent.RunAsync(userInput, thread: null, options, cancellationToken).ConfigureAwait(false) :
                await agent.RunAsync(thread: null, options, cancellationToken).ConfigureAwait(false);
        StringValue responseValue = FormulaValue.New(response.Messages.Last().ToString());

        this.AssignTarget(context, responseValue);
    }
}
