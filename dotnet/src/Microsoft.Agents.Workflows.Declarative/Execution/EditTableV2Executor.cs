// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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
        TableValue tableValue = (TableValue)table;

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
        }
        else if (changeType is RemoveItemOperation) // %%% SUPPORT
        {
        }
        else if (changeType is TakeFirstItemOperation) // %%% SUPPORT
        {
        }

        static RecordValue BuildRecord(RecordType recordType, FormulaValue value)
        {
            return FormulaValue.NewRecordFromFields(recordType, GetValues());

            IEnumerable<NamedValue> GetValues()
            {
                // %%% TODO: expression.StructuredRecordExpression.Properties ???
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
