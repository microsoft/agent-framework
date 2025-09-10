// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class RetrieveConversationMessagesExecutor(RetrieveConversationMessages model, DeclarativeWorkflowState state) :
    DeclarativeActionExecutor<RetrieveConversationMessages>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        await Task.Delay(0, cancellationToken).ConfigureAwait(false);

        return default;
    }
}
