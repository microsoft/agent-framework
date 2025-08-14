// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class EndConversationExecutor(EndConversation model) : WorkflowActionExecutor<EndConversation>(model)
{
    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        // %%% DIAGNOSTICS / STATE MANAGEMENT ???
        return new ValueTask();
    }
}
