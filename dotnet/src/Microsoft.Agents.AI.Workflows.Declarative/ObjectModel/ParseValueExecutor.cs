
// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.Extensions.Logging;
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
        object? sourceValue = expressionResult.Value.ToObject();
        try
        {
            object? parsedResult = sourceValue.ConvertType(targetType);
            parsedValue = parsedResult.ToFormula();
        }
        catch (Exception exception) when (
            expressionResult.Sensitivity == SensitivityLevel.Sensitive &&
            exception is FormatException or OverflowException or JsonException or DeclarativeActionException or DeclarativeModelException or ArgumentException or InvalidCastException or InvalidOperationException)
        {
            this.Logger.LogWarning(
                "Value conversion returned a blank result for action {ActionId} and target type {TargetType}.",
                this.Id,
                targetType.Type.Name);
            parsedValue = this.Model.ValueType.NewBlank();
        }

        await this.AssignAsync(this.Model.Variable.Path, parsedValue, context, expressionResult.Sensitivity).ConfigureAwait(false);

        return default;
    }
}
