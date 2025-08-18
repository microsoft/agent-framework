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

internal sealed class EditTableV2Executor(EditTableV2 model) : DeclarativeActionExecutor<EditTableV2>(model)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.ItemsVariable?.Path, $"{nameof(this.Model)}.{nameof(this.Model.ItemsVariable)}");

        FormulaValue table = this.State.Get(variablePath);
        if (table is not TableValue tableValue)
        {
            throw new WorkflowExecutionException($"Require '{variablePath.Format()}' to be a table, not: '{table.GetType().Name}'.");
        }

        EditTableOperation? changeType = this.Model.ChangeType;
        if (changeType is AddItemOperation addItemOperation)
        {
            ValueExpression addItemValue = Throw.IfNull(addItemOperation.Value, $"{nameof(this.Model)}.{nameof(this.Model.ChangeType)}");
            EvaluationResult<DataValue> expressionResult = this.State.ExpressionEngine.GetValue(addItemValue);
            RecordValue newRecord = BuildRecord(tableValue.Type.ToRecord(), expressionResult.Value.ToFormulaValue());
            await tableValue.AppendAsync(newRecord, cancellationToken).ConfigureAwait(false);
            this.AssignTarget(variablePath, tableValue);
        }
        else if (changeType is ClearItemsOperation)
        {
            await tableValue.ClearAsync(cancellationToken).ConfigureAwait(false);
            this.AssignTarget(variablePath, tableValue);
        }
        else if (changeType is RemoveItemOperation removeItemOperation)
        {
            ValueExpression removeItemValue = Throw.IfNull(removeItemOperation.Value, $"{nameof(this.Model)}.{nameof(this.Model.ChangeType)}");
            EvaluationResult<DataValue> expressionResult = this.State.ExpressionEngine.GetValue(removeItemValue);
            if (expressionResult.Value.ToFormulaValue() is TableValue removeItemTable)
            {
                await tableValue.RemoveAsync(removeItemTable?.Rows.Select(row => row.Value), all: true, cancellationToken).ConfigureAwait(false);
            }
        }
        else if (changeType is TakeFirstItemOperation)
        {
            this.AssignTarget(variablePath, tableValue.Rows.First().Value); // %%% TABLE OR RECORD ???
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
