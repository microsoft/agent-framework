
// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class ParseValueExecutor(ParseValue model) :
    WorkflowActionExecutor<ParseValue>(model)
{
    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");
        ValueExpression valueExpression = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");

        EvaluationResult<DataValue> result = this.Context.ExpressionEngine.GetValue(valueExpression, this.Context.Scopes);

        FormulaValue? parsedResult = null;

        if (result.Value is StringDataValue stringValue)
        {
            if (string.IsNullOrWhiteSpace(stringValue.Value))
            {
                parsedResult = FormulaValue.NewBlank();
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
            throw new WorkflowExecutionException($"Unable to parse {result.Value.GetType().Name}");
        }

        this.AssignTarget(this.Context, variablePath, parsedResult);

        return new ValueTask();
    }

    private static RecordValue ParseRecord(RecordDataType recordType, string rawText)
    {
        string jsonText = rawText.TrimJsonDelimiter();
        JsonDocument json = JsonDocument.Parse(jsonText);
        JsonElement currentElement = json.RootElement;
        return recordType.ParseRecord(currentElement); // %%% FIX / REMOVE ???
    }
}
