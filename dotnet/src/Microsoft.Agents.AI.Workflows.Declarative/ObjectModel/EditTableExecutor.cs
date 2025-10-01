﻿// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
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
                RecordValue newRecord = BuildRecord(tableValue.Type.ToRecord(), addResult.Value.ToFormula());
                await tableValue.AppendAsync(newRecord, cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(variablePath, newRecord, context).ConfigureAwait(false);
                break;
            case TableChangeType.Remove:
                ValueExpression removeItemValue = Throw.IfNull(this.Model.Value, $"{nameof(this.Model)}.{nameof(this.Model.Value)}");
                EvaluationResult<DataValue> removeResult = this.Evaluator.GetValue(removeItemValue);
                if (removeResult.Value is TableDataValue removeItemTable)
                {
                    await tableValue.RemoveAsync(removeItemTable?.Values.Select(row => row.ToRecordValue()), all: true, cancellationToken).ConfigureAwait(false);
                    await this.AssignAsync(variablePath, RecordValue.Empty(), context).ConfigureAwait(false);
                }
                break;
            case TableChangeType.Clear:
                await tableValue.ClearAsync(cancellationToken).ConfigureAwait(false);
                await this.AssignAsync(variablePath, FormulaValue.NewBlank(), context).ConfigureAwait(false);
                break;
            case TableChangeType.TakeFirst:
                RecordValue? firstRow = tableValue.Rows.FirstOrDefault()?.Value;
                if (firstRow is not null)
                {
                    await tableValue.RemoveAsync([firstRow], all: true, cancellationToken).ConfigureAwait(false);
                    await this.AssignAsync(variablePath, firstRow, context).ConfigureAwait(false);
                }
                break;
            case TableChangeType.TakeLast:
                RecordValue? lastRow = tableValue.Rows.LastOrDefault()?.Value;
                if (lastRow is not null)
                {
                    await tableValue.RemoveAsync([lastRow], all: true, cancellationToken).ConfigureAwait(false);
                    await this.AssignAsync(variablePath, lastRow, context).ConfigureAwait(false);
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
