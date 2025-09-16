// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class GotoExecutor(GotoAction model, WorkflowFormulaState state) :
    DeclarativeActionExecutor<GotoAction>(model, state)
{
    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        // No action needed - the edge will be followed automatically
        return default;
    }
}
