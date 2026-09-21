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

internal sealed class EditTableExecutor(EditTable model, WorkflowFormulaState state) : DeclarativeActionExecutor<EditTable>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.ItemsVariable?.Path, $"{nameof(this.Model)}.{nameof(this.Model.ItemsVariable)}");

        FormulaValue table = context.ReadState(variablePath);
        if (table is not TableValue tableValue)
        {
            throw this.Exception($"Require '{variablePath}' to be a table, not: '{table.GetType().Name}'.");
        }

        TableChangeType changeType = this.Model.ChangeType.Value;
        switch (this.Model.ChangeType.Value)
        {
            case TableChangeType.Add:
                ValueExpression addItemValue = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");
                EvaluationResult<DataValue> addResult = this.Evaluator.GetValue(addItemValue);
                FormulaValue addValue = addResult.Value.ToFormula();
                RecordType recordType = tableValue.Type.ToRecord();
                RecordValue newRecord;
                TableValue resultTable;
                if (!recordType.FieldNames.Any() && !tableValue.Rows.Any())
                {
                    newRecord = BuildRecordFromValue(addValue);
                    resultTable = FormulaValue.NewTable(newRecord.Type, newRecord);
                }
                else
                {
                    newRecord = BuildRecord(recordType, addValue);
                    await tableValue.AppendAsync(newRecord, cancellationToken).ConfigureAwait(false);
                    resultTable = tableValue;
                }
                await this.AssignAsync(variablePath, resultTable, context).ConfigureAwait(false);
                await this.AssignAsync(this.Model.ResultVariable?.Path, newRecord, context).ConfigureAwait(false);
                break;
            case TableChangeType.Remove:
                ValueExpression removeItemValue = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");
                EvaluationResult<DataValue> removeResult = this.Evaluator.GetValue(removeItemValue);
                if (removeResult.Value is TableDataValue removeItemTable)
                {
                    await tableValue.RemoveAsync(removeItemTable?.Values.Select(row => row.ToRecordValue()), all: true, cancellationToken).ConfigureAwait(false);
                    await this.AssignAsync(variablePath, tableValue, context).ConfigureAwait(false);
                    await this.AssignAsync(this.Model.ResultVariable?.Path, RecordValue.Empty(), context).ConfigureAwait(false);
                }
                break;
            case TableChangeType.Clear:
                await tableValue.ClearAsync(cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(variablePath, tableValue, context).ConfigureAwait(false);
                await this.AssignAsync(this.Model.ResultVariable?.Path, FormulaValue.NewBlank(), context).ConfigureAwait(false);
                break;
            case TableChangeType.TakeFirst:
                RecordValue? firstRow = tableValue.Rows.FirstOrDefault()?.Value;
                if (firstRow is not null)
                {
                    await tableValue.RemoveAsync([firstRow], all: true, cancellationToken).ConfigureAwait(false);
                    await this.AssignAsync(variablePath, tableValue, context).ConfigureAwait(false);
                    await this.AssignAsync(this.Model.ResultVariable?.Path, firstRow, context).ConfigureAwait(false);
                }
                else
                {
                    await this.AssignAsync(this.Model.ResultVariable?.Path, FormulaValue.NewBlank(), context).ConfigureAwait(false);
                }
                break;
            case TableChangeType.TakeLast:
                RecordValue? lastRow = tableValue.Rows.LastOrDefault()?.Value;
                if (lastRow is not null)
                {
                    await tableValue.RemoveAsync([lastRow], all: true, cancellationToken).ConfigureAwait(false);
                    await this.AssignAsync(variablePath, tableValue, context).ConfigureAwait(false);
                    await this.AssignAsync(this.Model.ResultVariable?.Path, lastRow, context).ConfigureAwait(false);
                }
                else
                {
                    await this.AssignAsync(this.Model.ResultVariable?.Path, FormulaValue.NewBlank(), context).ConfigureAwait(false);
                }
                break;
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
