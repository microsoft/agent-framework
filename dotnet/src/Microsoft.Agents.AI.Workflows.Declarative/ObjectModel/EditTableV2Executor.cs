// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class EditTableV2Executor(EditTableV2 model, WorkflowFormulaState state) : DeclarativeActionExecutor<EditTableV2>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(this.Model.ItemsVariable, $"{nameof(this.Model)}.{nameof(this.Model.ItemsVariable)}");

        FormulaValue table = context.ReadState(this.Model.ItemsVariable);
        if (table is not TableValue tableValue)
        {
            throw this.Exception($"Require '{this.Model.ItemsVariable.Path}' to be a table, not: '{table.GetType().Name}'.");
        }

        EditTableOperation? changeType = this.Model.ChangeType;
        if (changeType is AddItemOperation addItemOperation)
        {
            ValueExpression addItemValue = Throw.IfNull(addItemOperation.Value, $"{nameof(this.Model)}.{nameof(this.Model.ChangeType)}");
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(addItemValue);
            FormulaValue addValue = expressionResult.Value.ToFormula();
            RecordType recordType = tableValue.Type.ToRecord();
            TableValue resultTable;
            if (!recordType.FieldNames.Any() && !tableValue.Rows.Any())
            {
                RecordValue newRecord = BuildRecordFromValue(addValue);
                resultTable = FormulaValue.NewTable(newRecord.Type, newRecord);
            }
            else
            {
                RecordValue newRecord = BuildRecord(recordType, addValue);
                await tableValue.AppendAsync(newRecord, cancellationToken).ConfigureAwait(false);
                resultTable = tableValue;
            }
            await this.AssignAsync(this.Model.ItemsVariable, resultTable, context).ConfigureAwait(false);
        }
        else if (changeType is ClearItemsOperation)
        {
            await tableValue.ClearAsync(cancellationToken).ConfigureAwait(false);
            await this.AssignAsync(this.Model.ItemsVariable, tableValue, context).ConfigureAwait(false);
        }
        else if (changeType is RemoveItemOperation removeItemOperation)
        {
            ValueExpression removeItemValue = Throw.IfNull(removeItemOperation.Value, $"{nameof(this.Model)}.{nameof(this.Model.ChangeType)}");
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(removeItemValue);
            if (expressionResult.Value.ToFormula() is TableValue removeItemTable)
            {
                await tableValue.RemoveAsync(removeItemTable.Rows.Select(row => row.Value), all: true, cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(this.Model.ItemsVariable, tableValue, context).ConfigureAwait(false);
            }
        }
        else if (changeType is TakeLastItemOperation takeLastOperation)
        {
            RecordValue? lastRow = tableValue.Rows.LastOrDefault()?.Value;
            if (lastRow is not null)
            {
                await tableValue.RemoveAsync([lastRow], all: true, cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(this.Model.ItemsVariable, tableValue, context).ConfigureAwait(false);
                await this.AssignAsync(takeLastOperation.ResultVariable?.Path, lastRow, context).ConfigureAwait(false);
            }
            else
            {
                await this.AssignAsync(takeLastOperation.ResultVariable?.Path, FormulaValue.NewBlank(), context).ConfigureAwait(false);
            }
        }
        else if (changeType is TakeFirstItemOperation takeFirstOperation)
        {
            RecordValue? firstRow = tableValue.Rows.FirstOrDefault()?.Value;
            if (firstRow is not null)
            {
                await tableValue.RemoveAsync([firstRow], all: true, cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(this.Model.ItemsVariable, tableValue, context).ConfigureAwait(false);
                await this.AssignAsync(takeFirstOperation.ResultVariable?.Path, firstRow, context).ConfigureAwait(false);
            }
            else
            {
                await this.AssignAsync(takeFirstOperation.ResultVariable?.Path, FormulaValue.NewBlank(), context).ConfigureAwait(false);
            }
        }

        return default;

        static RecordValue BuildRecordFromValue(FormulaValue value) =>
            value is RecordValue recordValue ?
                recordValue :
                FormulaValue.NewRecordFromFields(new NamedValue("Value", value));

        static RecordValue BuildRecord(RecordType recordType, FormulaValue value)
        {
            return FormulaValue.NewRecordFromFields(recordType, GetValues());

            IEnumerable<NamedValue> GetValues()
            {
                foreach (NamedFormulaType fieldType in recordType.GetFieldTypes())
                {
                    if (value is RecordValue recordValue)
                    {
                        yield return new NamedValue(fieldType.Name, recordValue.GetField(fieldType.Name));
                    }
                    else
                    {
                        yield return new NamedValue(fieldType.Name, value);
                    }
                }
            }
        }
    }
}
