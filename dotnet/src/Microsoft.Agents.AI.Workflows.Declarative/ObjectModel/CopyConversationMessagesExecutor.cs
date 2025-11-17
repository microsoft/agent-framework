// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class CopyConversationMessagesExecutor(CopyConversationMessages model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<CopyConversationMessages>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(this.Model.ConversationId, $"{nameof(this.Model)}.{nameof(this.Model.ConversationId)}");
        string conversationId = this.Evaluator.GetValue(this.Model.ConversationId).Value;
        bool isWorkflowConversation = context.IsWorkflowConversation(conversationId, out string? _);

        IEnumerable<ChatMessage>? inputMessages = this.GetInputMessages();

        if (inputMessages is not null)
        {
            foreach (ChatMessage message in inputMessages)
            {
                await agentProvider.CreateMessageAsync(conversationId, message, cancellationToken).ConfigureAwait(false);
            }

            if (isWorkflowConversation)
            {
                await context.AddEventAsync(new AgentRunResponseEvent(this.Id, new AgentRunResponse([.. inputMessages])), cancellationToken).ConfigureAwait(false);
            }
        }

        return default;
    }

    private IEnumerable<ChatMessage>? GetInputMessages()
    {
        DataValue? messages = null;

        if (this.Model.Messages is not null)
        {
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.Model.Messages);
            messages = expressionResult.Value;
        }

        return messages?.ToChatMessages();
    }
}
