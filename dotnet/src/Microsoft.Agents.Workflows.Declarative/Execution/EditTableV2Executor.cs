// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class EditTableV2Executor(EditTableV2 model) : WorkflowActionExecutor<EditTableV2>(model)
{
    protected async override ValueTask ExecuteAsync(CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.ItemsVariable?.Path, $"{nameof(this.Model)}.{nameof(this.Model.ItemsVariable)}");

        FormulaValue table = this.Context.Scopes.Get(variablePath.VariableName!, WorkflowScopeType.Parse(variablePath.VariableScopeName));
        if (table is not TableValue tableValue)
        {
            throw new WorkflowExecutionException($"Require '{variablePath.Format()}' to be a table, not: '{table.GetType().Name}'.");
        }

        EditTableOperation? changeType = this.Model.ChangeType;
        if (changeType is AddItemOperation addItemOperation)
        {
            ValueExpression addItemValue = Throw.IfNull(addItemOperation.Value, $"{nameof(this.Model)}.{nameof(this.Model.ChangeType)}");
            EvaluationResult<DataValue> result = this.Context.ExpressionEngine.GetValue(addItemValue, this.Context.Scopes);
            RecordValue newRecord = BuildRecord(tableValue.Type.ToRecord(), result.Value.ToFormulaValue());
            await tableValue.AppendAsync(newRecord, cancellationToken).ConfigureAwait(false);
            this.AssignTarget(this.Context, variablePath, tableValue);
        }
        else if (changeType is ClearItemsOperation)
        {
            await tableValue.ClearAsync(cancellationToken).ConfigureAwait(false);
            this.AssignTarget(this.Context, variablePath, tableValue);
        }
        else if (changeType is RemoveItemOperation removeItemOperation)
        {
            ValueExpression removeItemValue = Throw.IfNull(removeItemOperation.Value, $"{nameof(this.Model)}.{nameof(this.Model.ChangeType)}");
            EvaluationResult<DataValue> result = this.Context.ExpressionEngine.GetValue(removeItemValue, this.Context.Scopes);
            if (result.Value.ToFormulaValue() is TableValue removeItemTable)
            {
                await tableValue.RemoveAsync(removeItemTable?.Rows.Select(row => row.Value), all: true, cancellationToken).ConfigureAwait(false);
            }
        }
        else if (changeType is TakeFirstItemOperation)
        {
            this.AssignTarget(this.Context, variablePath, tableValue.Rows.First().Value); // %%% TABLE OR RECORD ???
        }

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
