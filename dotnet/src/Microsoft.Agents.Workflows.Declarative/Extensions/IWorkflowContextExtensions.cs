// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class IWorkflowContextExtensions
{
    public static ValueTask QueueStateUpdateAsync<TValue>(this IWorkflowContext context, PropertyPath variablePath, TValue? value) =>
        context.QueueStateUpdateAsync(Throw.IfNull(variablePath.VariableName), value, Throw.IfNull(variablePath.VariableScopeName));

    public static async Task<WorkflowFormulaState> GetStateAsync(this IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (context is DeclarativeWorkflowContext declarativeContext)
        {
            return declarativeContext.State;
        }

        WorkflowFormulaState state = new(RecalcEngineFactory.Create());

        await state.RestoreAsync(context, cancellationToken).ConfigureAwait(false);

        return state;
    }
}
