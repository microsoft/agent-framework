// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class RetrieveConversationMessagesExecutor(RetrieveConversationMessages model, ResponseAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<RetrieveConversationMessages>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(this.Model.Messages);
        Throw.IfNull(this.Model.ConversationId, $"{nameof(this.Model)}.{nameof(this.Model.ConversationId)}");

        string conversationId = this.Evaluator.GetValue(this.Model.ConversationId).Value;

        List<ChatMessage> messages = [];
        await foreach (ChatMessage message in agentProvider.GetMessagesAsync(
            conversationId,
            limit: this.GetLimit(),
            after: this.GetMessage(this.Model.MessageAfter),
            before: this.GetMessage(this.Model.MessageBefore),
            newestFirst: this.IsDescending(),
            cancellationToken).ConfigureAwait(false))
        {
            messages.Add(message);
        }

        await this.AssignAsync(this.Model.Messages.Path, messages.ToTable(), context).ConfigureAwait(false);

        return default;
    }

    private int? GetLimit()
    {
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
        AgentMessageSortOrderWrapper sortOrderWrapper = this.Evaluator.GetValue(this.Model.SortOrder).Value;

        return sortOrderWrapper.Value == AgentMessageSortOrder.NewestFirst;
    }
}
