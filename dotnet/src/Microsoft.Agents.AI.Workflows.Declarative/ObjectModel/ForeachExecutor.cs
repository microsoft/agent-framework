// Copyright (c) Microsoft. All rights reserved.

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

internal sealed class ForeachExecutor : DeclarativeActionExecutor<Foreach>
{
    public static class Steps
    {
        public static string Start(string id) => $"{id}_{nameof(Start)}";
        public static string Next(string id) => $"{id}_{nameof(Next)}";
        public static string End(string id) => $"{id}_{nameof(End)}";
    }

    // State keys for checkpoint persistence of iteration progress.
    private const string IndexStateKey = nameof(_index);
    private const string ValuesStateKey = nameof(_values);
    private const string HasValueStateKey = nameof(HasValue);

    private int _index;
    private FormulaValue[] _values;

    public ForeachExecutor(Foreach model, WorkflowFormulaState state)
        : base(model, state)
    {
        this._values = [];
    }

    public bool HasValue { get; private set; }

    protected override bool IsDiscreteAction => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(this.Model.Items, $"{nameof(this.Model)}.{nameof(this.Model.Items)}");

        this._index = 0;

        EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.Model.Items);
        if (expressionResult.Value is TableDataValue tableValue)
        {
            this._values = [.. tableValue.Values.Select(ToLoopValue)];
        }
        else
        {
            this._values = [expressionResult.Value.ToFormula()];
        }

        await this.ResetStateAsync(context, cancellationToken).ConfigureAwait(false);

        return default;
    }

    public async ValueTask TakeNextAsync(IWorkflowContext context, object? _, CancellationToken cancellationToken)
    {
        if (this.HasValue = this._index < this._values.Length)
        {
            FormulaValue value = this._values[this._index];

            await context.QueueStateUpdateAsync(Throw.IfNull(this.Model.Value), value, cancellationToken).ConfigureAwait(false);

            if (this.Model.Index is not null)
            {
                await context.QueueStateUpdateAsync(this.Model.Index.Path, FormulaValue.New(this._index), cancellationToken).ConfigureAwait(false);
            }

            this._index++;
        }
    }

    public async ValueTask CompleteAsync(IWorkflowContext context, object? _, CancellationToken cancellationToken)
    {
        try
        {
            await this.ResetStateAsync(context, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task ResetStateAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        await context.QueueStateResetAsync(Throw.IfNull(this.Model.Value), cancellationToken).ConfigureAwait(false);
        if (this.Model.Index is not null)
        {
            await context.QueueStateResetAsync(this.Model.Index, cancellationToken).ConfigureAwait(false);
        }
    }

    // Power Fx wraps scalar array literals (`=[1, 2, 3]`) as `Table({Value: 1}, ...)`. Unwrap that single-column
    // `Value`-record shape so `Local.LoopValue` is the scalar; multi-field and other shapes pass through unchanged.
    private static FormulaValue ToLoopValue(DataValue value) =>
        value is RecordDataValue record
            && record.Properties.Count == 1
            && record.Properties.TryGetValue("Value", out DataValue? singleColumn)
                ? singleColumn.ToFormula()
                : value.ToFormula();

    /// <inheritdoc/>
    /// <remarks>
    /// Persists the iteration cursor (<see cref="_index"/>), the materialized item snapshot
    /// (<see cref="_values"/> as <see cref="PortableValue"/>[]), and <see cref="HasValue"/> so a
    /// foreach loop can resume mid-iteration after a checkpoint (e.g. when a <c>Question</c>
    /// inside the loop body pauses the workflow and the executor is re-instantiated on resume).
    /// </remarks>
    protected override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        PortableValue[] portableValues = [.. this._values.Select(value => new PortableValue(value.AsPortable()))];

        await context.QueueStateUpdateAsync(IndexStateKey, this._index, cancellationToken: cancellationToken).ConfigureAwait(false);
        await context.QueueStateUpdateAsync(ValuesStateKey, portableValues, cancellationToken: cancellationToken).ConfigureAwait(false);
        await context.QueueStateUpdateAsync(HasValueStateKey, this.HasValue, cancellationToken: cancellationToken).ConfigureAwait(false);

        await base.OnCheckpointingAsync(context, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Restores the iteration cursor, item snapshot, and <see cref="HasValue"/> recorded by
    /// <see cref="OnCheckpointingAsync"/>. The presence of the values snapshot is the source of
    /// truth for "this foreach was previously checkpointed"; if it is absent the executor keeps
    /// its constructor defaults (fresh-start semantics).
    /// </remarks>
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);

        PortableValue[]? savedValues =
            await context.ReadStateAsync<PortableValue[]>(ValuesStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
        if (savedValues is null)
        {
            return;
        }

        this._values = [.. savedValues.Select(value => value.ToFormula())];
        this._index = await context.ReadStateAsync<int>(IndexStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
        this.HasValue = await context.ReadStateAsync<bool>(HasValueStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
    }
}
