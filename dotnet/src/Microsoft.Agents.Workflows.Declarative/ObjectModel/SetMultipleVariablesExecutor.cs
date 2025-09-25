// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class SetMultipleVariablesExecutor(SetMultipleVariables model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<SetMultipleVariables>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        foreach (VariableAssignment assignment in this.Model.Assignments)
        {
            if (assignment.Variable is null)
            {
                continue;
            }

            if (assignment.Value is null)
            {
                await this.AssignAsync(assignment.Variable, FormulaValue.NewBlank(), context).ConfigureAwait(false);
            }
            else
            {
                EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(assignment.Value);

                await this.AssignAsync(assignment.Variable, expressionResult.Value.ToFormula(), context).ConfigureAwait(false);
            }
        }

        return default;
    }
}
