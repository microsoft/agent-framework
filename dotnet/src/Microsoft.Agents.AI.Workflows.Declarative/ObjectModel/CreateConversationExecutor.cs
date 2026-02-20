// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class CreateConversationExecutor(CreateConversation model, ResponseAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<CreateConversation>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(this.Model.ConversationId, $"{nameof(this.Model)}.{nameof(this.Model.ConversationId)}");

        string conversationId = await agentProvider.CreateConversationAsync(cancellationToken).ConfigureAwait(false);
        await this.AssignAsync(this.Model.ConversationId.Path, FormulaValue.New(conversationId), context).ConfigureAwait(false);
        await context.QueueConversationUpdateAsync(conversationId, cancellationToken).ConfigureAwait(false);

        return default;
    }
}
