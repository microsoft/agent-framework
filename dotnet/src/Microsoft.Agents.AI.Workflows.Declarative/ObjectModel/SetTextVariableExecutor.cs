// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class SetTextVariableExecutor(SetTextVariable model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<SetTextVariable>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (this.Model.Value is null)
        {
            await this.AssignAsync(this.Model.Variable?.Path, FormulaValue.NewBlank(), context).ConfigureAwait(false);
        }
        else
        {
            FormulaValue expressionResult = FormulaValue.New(this.Engine.Format(this.Model.Value));

            await this.AssignAsync(this.Model.Variable?.Path, expressionResult, context).ConfigureAwait(false);
        }

        return default;
    }
}
