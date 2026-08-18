// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
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
    private readonly ForeachExecutionOptions _executionOptions;
    private readonly DeclarativeWorkflowOptions? _workflowOptions;
    private readonly WorkflowFormulaState _workflowState;

    public ForeachExecutor(Foreach model, WorkflowFormulaState state, DeclarativeWorkflowOptions? workflowOptions = null)
        : base(model, state)
    {
        this._values = [];
        this._executionOptions = ForeachExecutionOptions.Parse(model);
        this._workflowOptions = workflowOptions;
        this._workflowState = state;

        if (this._executionOptions.IsParallel)
        {
            if (workflowOptions is null)
            {
                throw new DeclarativeModelException($"Parallel Foreach '{model.Id.Value}' requires workflow execution options.");
            }

            ParallelForeachIterationRunner.ValidateBody(model);
        }
    }

    public bool HasValue { get; private set; }

    public bool IsParallel => this._executionOptions.IsParallel;

    protected override bool IsDiscreteAction => this.IsParallel;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return this.IsParallel
            ? await this.ExecuteParallelAsync(context, cancellationToken).ConfigureAwait(false)
            : await this.ExecuteSequentialAsync(context, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask<object?> ExecuteSequentialAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        Throw.IfNull(this.Model.Items, $"{nameof(this.Model)}.{nameof(this.Model.Items)}");

        this._index = 0;
        this._values = this.GetValues();

        await this.ResetStateAsync(context, cancellationToken).ConfigureAwait(false);

        return default;
    }

    private async ValueTask<object?> ExecuteParallelAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        Throw.IfNull(this.Model.Items, $"{nameof(this.Model)}.{nameof(this.Model.Items)}");
        DeclarativeWorkflowOptions workflowOptions = Throw.IfNull(this._workflowOptions);
        FormulaValue[] values = this.GetValues();

        await this.ResetStateAsync(context, cancellationToken).ConfigureAwait(false);

        try
        {
            if (values.Length == 0)
            {
                return default;
            }

            WorkflowStateSnapshot stateSnapshot = this._workflowState.CaptureSnapshot();
            ParallelForeachIterationResult?[] iterationResults = new ParallelForeachIterationResult?[values.Length];
            Exception?[] iterationFailures = new Exception?[values.Length];
            int nextIndex = -1;

            void RecordIterationFailure(int index, Exception exception) =>
                Interlocked.CompareExchange(ref iterationFailures[index], exception, null);

            using CancellationTokenSource groupCancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            int workerCount = Math.Min(values.Length, this._executionOptions.MaxParallelism);
            Task[] workers =
            [
                .. Enumerable.Range(0, workerCount).Select(_ => RunWorkerAsync()),
            ];

            await Task.WhenAll(workers).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();

            List<Exception> failures = [];
            for (int index = 0; index < iterationFailures.Length; index++)
            {
                if (iterationFailures[index] is Exception exception)
                {
                    failures.Add(
                        new DeclarativeActionException(
                            $"Parallel Foreach '{this.Id}' iteration {index} failed.",
                            exception));
                }
            }

            if (failures.Count > 0)
            {
                throw new AggregateException($"Parallel Foreach '{this.Id}' failed.", failures);
            }

            WorkflowConversationMessageBuffer? parentConversationBuffer =
                (context as DeclarativeWorkflowContext)?.ConversationMessageBuffer;
            string? workflowConversationId = parentConversationBuffer is null ? context.GetWorkflowConversation() : null;

            foreach (ParallelForeachIterationResult iterationResult in iterationResults.Cast<ParallelForeachIterationResult>())
            {
                foreach (WorkflowStateChange stateChange in iterationResult.StateChanges)
                {
                    await CommitStateChangeAsync(context, stateChange, cancellationToken).ConfigureAwait(false);
                }

                foreach (WorkflowEvent workflowEvent in iterationResult.Events)
                {
                    await context.AddEventAsync(workflowEvent, cancellationToken).ConfigureAwait(false);
                }

                if (iterationResult.ConversationMessages.Length > 0)
                {
                    if (parentConversationBuffer is not null)
                    {
                        foreach (ChatMessage message in iterationResult.ConversationMessages)
                        {
                            parentConversationBuffer.Add(message);
                        }
                    }
                    else if (workflowConversationId is null)
                    {
                        throw new DeclarativeActionException(
                            $"Parallel Foreach '{this.Id}' produced workflow-conversation messages without a workflow conversation.");
                    }
                    else
                    {
                        foreach (ChatMessage message in iterationResult.ConversationMessages)
                        {
                            await workflowOptions.AgentProvider.CreateMessageAsync(
                                workflowConversationId,
                                message,
                                cancellationToken).ConfigureAwait(false);
                        }
                    }
                }
            }

            return default;

            async Task RunWorkerAsync()
            {
                while (!groupCancellation.IsCancellationRequested)
                {
                    int iterationIndex = Interlocked.Increment(ref nextIndex);
                    // Use an unsigned comparison so an exhausted allocator cannot wrap around and
                    // address a negative array index when an extreme item count is combined with
                    // multiple workers.
                    if ((uint)iterationIndex >= (uint)values.Length)
                    {
                        return;
                    }

                    try
                    {
                        iterationResults[iterationIndex] = await ParallelForeachIterationRunner.RunAsync(
                            this.Model,
                            values[iterationIndex],
                            iterationIndex,
                            stateSnapshot,
                            workflowOptions,
                            this._executionOptions.IterationTimeout,
                            exception => RecordIterationFailure(iterationIndex, exception),
                            groupCancellation.Token).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException) when (groupCancellation.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
                    {
                        return;
                    }
                    catch (Exception exception)
                    {
                        RecordIterationFailure(iterationIndex, exception);
                        groupCancellation.Cancel();
                        return;
                    }
                }
            }
        }
        finally
        {
            await this.ResetStateAsync(context, CancellationToken.None).ConfigureAwait(false);
        }
    }

    private static ValueTask CommitStateChangeAsync(
        IWorkflowContext context,
        WorkflowStateChange stateChange,
        CancellationToken cancellationToken)
    {
        FormulaValue value = stateChange.Value.ToFormula();
        return stateChange.ScopeName switch
        {
            VariableScopeNames.System => context.QueueSystemUpdateAsync(stateChange.VariableName, value, cancellationToken),
            VariableScopeNames.Environment => context.QueueEnvironmentUpdateAsync(stateChange.VariableName, value, cancellationToken),
            _ => context.QueueStateUpdateAsync(stateChange.VariableName, value, stateChange.ScopeName, cancellationToken),
        };
    }

    private FormulaValue[] GetValues()
    {
        EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(Throw.IfNull(this.Model.Items));
        return expressionResult.Value is TableDataValue tableValue
            ? [.. tableValue.Values.Select(ToLoopValue)]
            : [expressionResult.Value.ToFormula()];
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
        if (this.IsParallel)
        {
            await base.OnCheckpointingAsync(context, cancellationToken).ConfigureAwait(false);
            return;
        }

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

        if (this.IsParallel)
        {
            return;
        }

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
