
// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class ParseValueExecutor(ParseValue model, WorkflowFormulaState state) :
    DeclarativeActionExecutor<ParseValue>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");
        ValueExpression valueExpression = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");

        EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(valueExpression);

        FormulaValue parsedValue;
        if (this.Model.ValueType is not null)
        {
            VariableType targetType = new(this.Model.ValueType);
            object? parsedResult = expressionResult.Value.ToObject().ConvertType(targetType);
            parsedValue = parsedResult.ToFormula();
        }
        else
        {
            parsedValue = expressionResult.Value.ToFormula();
        }

        await this.AssignAsync(variablePath, parsedValue, context).ConfigureAwait(false);

        return default;
    }
}
