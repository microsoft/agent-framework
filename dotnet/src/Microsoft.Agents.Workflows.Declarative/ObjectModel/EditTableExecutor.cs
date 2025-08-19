// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class EditTableExecutor(EditTable model) : DeclarativeActionExecutor<EditTable>(model)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.ItemsVariable?.Path, $"{nameof(this.Model)}.{nameof(this.Model.ItemsVariable)}");

        FormulaValue table = this.State.Get(variablePath);
        if (table is not TableValue tableValue)
        {
            throw new WorkflowExecutionException($"Require '{variablePath.Format()}' to be a table, not: '{table.GetType().Name}'.");
        }

        TableChangeType changeType = this.Model.ChangeType.Value;
        switch (this.Model.ChangeType.Value)
        {
            case TableChangeType.Add:
                ValueExpression addItemValue = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");
                EvaluationResult<DataValue> addResult = this.State.ExpressionEngine.GetValue(addItemValue);
                RecordValue newRecord = BuildRecord(tableValue.Type.ToRecord(), addResult.Value.ToFormulaValue());
                await tableValue.AppendAsync(newRecord, cancellationToken).ConfigureAwait(false);
                this.AssignTarget(variablePath, newRecord);
                break;
            case TableChangeType.Remove:
                ValueExpression removeItemValue = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");
                EvaluationResult<DataValue> removeResult = this.State.ExpressionEngine.GetValue(removeItemValue);
                if (removeResult.Value is TableDataValue removeItemTable)
                {
                    await tableValue.RemoveAsync(removeItemTable?.Values.Select(row => row.ToRecordValue()), all: true, cancellationToken).ConfigureAwait(false);
                    this.AssignTarget(variablePath, RecordValue.Empty());
                }
                break;
            case TableChangeType.Clear:
                await tableValue.ClearAsync(cancellationToken).ConfigureAwait(false);
                this.AssignTarget(variablePath, FormulaValue.NewBlank());
                break;
            case TableChangeType.TakeFirst:
                RecordValue? firstRow = tableValue.Rows.FirstOrDefault()?.Value;
                if (firstRow is not null)
                {
                    await tableValue.RemoveAsync([firstRow], all: true, cancellationToken).ConfigureAwait(false);
                    this.AssignTarget(variablePath, firstRow);
                }
                break;
            case TableChangeType.TakeLast:
                RecordValue? lastRow = tableValue.Rows.LastOrDefault()?.Value;
                if (lastRow is not null)
                {
                    await tableValue.RemoveAsync([lastRow], all: true, cancellationToken).ConfigureAwait(false);
                    this.AssignTarget(variablePath, lastRow);
                }
                break;
        }

        return default;

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
