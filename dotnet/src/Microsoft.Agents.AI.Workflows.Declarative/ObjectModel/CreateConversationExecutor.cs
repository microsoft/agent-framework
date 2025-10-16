// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class CreateConversationExecutor(CreateConversation model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<CreateConversation>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string conversationId = await agentProvider.CreateConversationAsync(cancellationToken).ConfigureAwait(false);
        await this.AssignAsync(this.Model.ConversationId?.Path, FormulaValue.New(conversationId), context).ConfigureAwait(false);
        await context.QueueConversationUpdateAsync(conversationId, cancellationToken).ConfigureAwait(false);

        return default;
    }
}
