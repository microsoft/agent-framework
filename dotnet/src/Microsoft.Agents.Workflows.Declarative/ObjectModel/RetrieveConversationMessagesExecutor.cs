// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class RetrieveConversationMessagesExecutor(RetrieveConversationMessages model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<RetrieveConversationMessages>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        string conversationId = this.Evaluator.GetValue(Throw.IfNull(this.Model.ConversationId, $"{nameof(this.Model)}.{nameof(this.Model.ConversationId)}")).Value;

        ChatMessage[] messages = await agentProvider.GetMessagesAsync(
            conversationId,
            limit: this.GetLimit(),
            after: this.GetMessage(this.Model.MessageAfter),
            before: this.GetMessage(this.Model.MessageBefore),
            newestFirst: this.IsDescending(),
            cancellationToken).ToArrayAsync(cancellationToken).ConfigureAwait(false);

        await this.AssignAsync(this.Model.Messages?.Path, messages.ToTable(), context).ConfigureAwait(false);

        return default;
    }

    private int? GetLimit()
    {
        if (this.Model.Limit is null)
        {
            return null;
        }

        long limit = this.Evaluator.GetValue(this.Model.Limit).Value;
        return Convert.ToInt32(Math.Min(limit, 100));
    }

    private string? GetMessage(StringExpression? messagExpression)
    {
        if (messagExpression is null)
        {
            return null;
        }

        return this.Evaluator.GetValue(messagExpression).Value;
    }

    private bool IsDescending()
    {
        if (this.Model.SortOrder is null)
        {
            return false;
        }

        AgentMessageSortOrderWrapper sortOrderWrapper = this.Evaluator.GetValue(this.Model.SortOrder).Value;

        return sortOrderWrapper.Value == AgentMessageSortOrder.NewestFirst;
    }
}
