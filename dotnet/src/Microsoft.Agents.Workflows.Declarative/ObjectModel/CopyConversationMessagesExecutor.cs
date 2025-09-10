// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class CopyConversationMessagesExecutor(CopyConversationMessages model, DeclarativeWorkflowState state) :
    DeclarativeActionExecutor<CopyConversationMessages>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        await Task.Delay(0, cancellationToken).ConfigureAwait(false);

        return default;
    }
}
