// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class SetTextVariableExecutor(SetTextVariable model) : DeclarativeActionExecutor<SetTextVariable>(model)
{
    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");

        if (this.Model.Value is null)
        {
            this.AssignTarget(variablePath, FormulaValue.NewBlank());
        }
        else
        {
            FormulaValue expressionResult = FormulaValue.New(this.State.Format(this.Model.Value));

            this.AssignTarget(variablePath, expressionResult);
        }

        return default;
    }
}
