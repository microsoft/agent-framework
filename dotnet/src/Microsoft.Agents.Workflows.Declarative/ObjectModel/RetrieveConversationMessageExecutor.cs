// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class RetrieveConversationMessageExecutor(RetrieveConversationMessage model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<RetrieveConversationMessage>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        string conversationId = this.Evaluator.GetValue(Throw.IfNull(this.Model.ConversationId, $"{nameof(this.Model)}.{nameof(this.Model.ConversationId)}")).Value;
        string messageId = this.Evaluator.GetValue(Throw.IfNull(this.Model.MessageId, $"{nameof(this.Model)}.{nameof(this.Model.MessageId)}")).Value;

        ChatMessage message = await agentProvider.GetMessageAsync(conversationId, messageId, cancellationToken).ConfigureAwait(false);

        await this.AssignAsync(this.Model.Message?.Path, message.ToRecord(), context).ConfigureAwait(false);

        return default;
    }
}
