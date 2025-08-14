// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class SetTextVariableExecutor(SetTextVariable model) : WorkflowActionExecutor<SetTextVariable>(model)
{
    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");

        if (this.Model.Value is null)
        {
            this.AssignTarget(this.Context, variablePath, FormulaValue.NewBlank());
        }
        else
        {
            FormulaValue result = FormulaValue.New(this.Context.Engine.Format(this.Model.Value));

            this.AssignTarget(this.Context, variablePath, result);
        }

        return new ValueTask();
    }
}
