
// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class ParseValueExecutor(ParseValue model, DeclarativeWorkflowState state) :
    DeclarativeActionExecutor<ParseValue>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");
        ValueExpression valueExpression = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");

        EvaluationResult<DataValue> expressionResult = this.State.ExpressionEngine.GetValue(valueExpression);

        FormulaValue? parsedResult = null;

        if (expressionResult.Value is RecordDataValue recordValue)
        {
            parsedResult = recordValue.ToFormulaValue();
        }
        else if (expressionResult.Value is StringDataValue stringValue)
        {
            if (string.IsNullOrWhiteSpace(stringValue.Value))
            {
                parsedResult = FormulaValue.NewBlank(expressionResult.Value.GetDataType().ToFormulaType());
            }
            else
            {
                parsedResult =
                    this.Model.ValueType switch
                    {
                        StringDataType => StringValue.New(stringValue.Value),
                        NumberDataType => NumberValue.New(stringValue.Value),
                        BooleanDataType => BooleanValue.New(stringValue.Value),
                        RecordDataType recordType => ParseRecord(recordType, stringValue.Value),
                        _ => null
                    };
            }
        }

        if (parsedResult is null)
        {
            throw this.Exception("Unable to parse value.");
        }

        await this.AssignAsync(variablePath, parsedResult, context).ConfigureAwait(false);

        return default;

        RecordValue ParseRecord(RecordDataType recordType, string rawText)
        {
            string jsonText = rawText.TrimJsonDelimiter();
            JsonDocument json = JsonDocument.Parse(jsonText);
            JsonElement currentElement = json.RootElement;
            try
            {
                return recordType.ParseRecord(currentElement);
            }
            catch (Exception exception)
            {
                throw this.Exception("Failed to parse value.", exception);
            }
        }
    }
}
