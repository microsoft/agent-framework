// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class EditTableV2Executor(EditTableV2 model, WorkflowFormulaState state) : DeclarativeActionExecutor<EditTableV2>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.ItemsVariable?.Path, $"{nameof(this.Model)}.{nameof(this.Model.ItemsVariable)}");

        FormulaValue table = context.ReadState(variablePath);
        if (table is not TableValue tableValue)
        {
            throw this.Exception($"Require '{variablePath}' to be a table, not: '{table.GetType().Name}'.");
        }

        EditTableOperation? changeType = this.Model.ChangeType;
        if (changeType is AddItemOperation addItemOperation)
        {
            ValueExpression addItemValue = Throw.IfNull(addItemOperation.Value, $"{nameof(this.Model)}.{nameof(this.Model.ChangeType)}");
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(addItemValue);
            RecordValue newRecord = BuildRecord(tableValue.Type.ToRecord(), expressionResult.Value.ToFormula());
            await tableValue.AppendAsync(newRecord, cancellationToken).ConfigureAwait(false);
            await this.AssignAsync(variablePath, newRecord, context).ConfigureAwait(false);
        }
        else if (changeType is ClearItemsOperation)
        {
            await tableValue.ClearAsync(cancellationToken).ConfigureAwait(false);
            await this.AssignAsync(variablePath, FormulaValue.NewBlank(), context).ConfigureAwait(false);
        }
        else if (changeType is RemoveItemOperation removeItemOperation)
        {
            ValueExpression removeItemValue = Throw.IfNull(removeItemOperation.Value, $"{nameof(this.Model)}.{nameof(this.Model.ChangeType)}");
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(removeItemValue);
            if (expressionResult.Value.ToFormula() is TableValue removeItemTable)
            {
                await tableValue.RemoveAsync(removeItemTable?.Rows.Select(row => row.Value), all: true, cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(variablePath, FormulaValue.NewBlank(), context).ConfigureAwait(false);
            }
        }
        else if (changeType is TakeLastItemOperation)
        {
            RecordValue? lastRow = tableValue.Rows.LastOrDefault()?.Value;
            if (lastRow is not null)
            {
                await tableValue.RemoveAsync([lastRow], all: true, cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(variablePath, lastRow, context).ConfigureAwait(false);
            }
        }
        else if (changeType is TakeFirstItemOperation)
        {
            RecordValue? firstRow = tableValue.Rows.FirstOrDefault()?.Value;
            if (firstRow is not null)
            {
                await tableValue.RemoveAsync([firstRow], all: true, cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(variablePath, firstRow, context).ConfigureAwait(false);
            }
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
