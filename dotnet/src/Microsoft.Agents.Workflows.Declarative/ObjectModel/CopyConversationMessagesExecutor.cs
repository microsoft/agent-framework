// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class CopyConversationMessagesExecutor(CopyConversationMessages model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<CopyConversationMessages>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        string conversationId = this.Evaluator.GetValue(Throw.IfNull(this.Model.ConversationId, $"{nameof(this.Model)}.{nameof(this.Model.ConversationId)}")).Value;
        DataValue? inputMessages = this.GetInputMessages();

        if (inputMessages is not null)
        {
            foreach (ChatMessage message in inputMessages.ToChatMessages())
            {
                await agentProvider.CreateMessageAsync(conversationId, message, cancellationToken).ConfigureAwait(false);
            }
        }

        return default;
    }

    private DataValue? GetInputMessages()
    {
        DataValue? messages = null;

        if (this.Model.Messages is not null)
        {
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.Model.Messages);
            messages = expressionResult.Value;
        }

        return messages;
    }
}
