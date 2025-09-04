// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class SetTextVariableExecutor(SetTextVariable model, DeclarativeWorkflowState state)
    : DeclarativeActionExecutor<SetTextVariable>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");

        if (this.Model.Value is null)
        {
            await this.AssignAsync(variablePath, FormulaValue.NewBlank(), context).ConfigureAwait(false);
        }
        else
        {
            FormulaValue expressionResult = FormulaValue.New(this.State.Format(this.Model.Value));

            await this.AssignAsync(variablePath, expressionResult, context).ConfigureAwait(false);
        }

        return default;
    }
}
