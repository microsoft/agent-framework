
// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class ParseValueExecutor(ParseValue model, WorkflowFormulaState state) :
    DeclarativeActionExecutor<ParseValue>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(this.Model.ValueType, $"{nameof(this.Model)}.{nameof(model.ValueType)}");
        Throw.IfNull(this.Model.Variable, $"{nameof(this.Model)}.{nameof(model.Variable)}");
        ValueExpression valueExpression = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");

        EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(valueExpression);

        FormulaValue parsedValue;
        VariableType targetType = new(this.Model.ValueType);
        object? parsedResult = expressionResult.Value.ToObject().ConvertType(targetType);
        parsedValue = parsedResult.ToFormula();

        await this.AssignAsync(this.Model.Variable.Path, parsedValue, context).ConfigureAwait(false);

        return default;
    }
}
