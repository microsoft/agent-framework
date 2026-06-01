// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="ForeachExecutor"/>.
/// </summary>
public sealed class ForeachExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void ForeachThrowsWhenModelInvalid() =>
        // Arrange, Act & Assert
        Assert.Throws<DeclarativeModelException>(() => new ForeachExecutor(new Foreach(), this.State));

    [Fact]
    public void ForeachNamingConvention()
    {
        // Arrange
        string testId = this.CreateActionId().Value;

        // Act
        string startStep = ForeachExecutor.Steps.Start(testId);
        string nextStep = ForeachExecutor.Steps.Next(testId);
        string endStep = ForeachExecutor.Steps.End(testId);

        // Assert
        Assert.Equal($"{testId}_{nameof(ForeachExecutor.Steps.Start)}", startStep);
        Assert.Equal($"{testId}_{nameof(ForeachExecutor.Steps.Next)}", nextStep);
        Assert.Equal($"{testId}_{nameof(ForeachExecutor.Steps.End)}", endStep);
    }

    [Fact]
    public async Task ForeachInvokedWithSingleValueAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachInvokedWithSingleValueAsync),
            items: ValueExpression.Literal(new NumberDataValue(42)),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachInvokedWithTableValueAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachInvokedWithTableValueAsync),
            items: ValueExpression.Literal(DataValue.EmptyTable),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachInvokedWithIndexAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue", "CurrentIndex");
        TableDataValue tableValue = DataValue.TableFromRecords(
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(1))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(2))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(3))));

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachInvokedWithIndexAsync),
            items: ValueExpression.Literal(tableValue),
            valueName: "CurrentValue",
            indexName: "CurrentIndex");
    }

    [Fact]
    public async Task ForeachInvokedWithExpressionAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");
        this.State.Set("SourceArray", FormulaValue.NewTable(RecordType.Empty()));

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachInvokedWithExpressionAsync),
            items: ValueExpression.Variable(PropertyPath.TopicVariable("SourceArray")),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachTakeNextAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");
        this.State.Set(
            "SourceArray",
            FormulaValue.NewTable(
                RecordType.Empty(),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(10))),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(20))),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(30)))));

        // Act & Assert
        await this.TakeNextTestAsync(
            displayName: nameof(ForeachTakeNextAsync),
            items: ValueExpression.Variable(PropertyPath.TopicVariable("SourceArray")),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachTakeNextWithIndexAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue", "CurrentIndex");
        this.State.Set(
            "SourceArray",
            FormulaValue.NewTable(
                RecordType.Empty(),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(10))),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(20))),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(30)))));

        // Act & Assert
        await this.TakeNextTestAsync(
            displayName: nameof(ForeachTakeNextWithIndexAsync),
            items: ValueExpression.Variable(PropertyPath.TopicVariable("SourceArray")),
            valueName: "CurrentValue",
            indexName: "CurrentIndex");
    }

    [Fact]
    public async Task ForeachTakeLastAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");
        this.State.Set(
            "SourceArray",
            FormulaValue.NewTable(
                RecordType.Empty(),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(10)))));

        // Act & Assert
        await this.TakeNextTestAsync(
            displayName: nameof(ForeachTakeLastAsync),
            items: ValueExpression.Variable(PropertyPath.TopicVariable("SourceArray")),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachTakeNextWhenDoneAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");

        // Act & Assert
        await this.TakeNextTestAsync(
            displayName: nameof(ForeachTakeNextWhenDoneAsync),
            items: ValueExpression.Literal(DataValue.EmptyTable),
            valueName: "CurrentValue",
            indexName: null,
            expectValue: false);
    }

    [Fact]
    public async Task ForeachCompletedWithoutIndexAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");

        // Act & Assert
        await this.CompletedTestAsync(
            displayName: nameof(ForeachCompletedWithoutIndexAsync),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachCompletedWithIndexAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue", "CurrentIndex");

        // Act & Assert
        await this.CompletedTestAsync(
            displayName: nameof(ForeachCompletedWithIndexAsync),
            valueName: "CurrentValue",
            indexName: "CurrentIndex");
    }

    /// <summary>
    /// Regression test for GH-5009: a <see cref="ForeachExecutor"/> that is re-instantiated
    /// during checkpoint restore (e.g. cross-process resume after a <c>Question</c> inside the
    /// loop body) must continue iterating from where it left off, not exit after the first
    /// iteration.
    /// </summary>
    [Fact]
    public async Task ForeachStateRestoredAcrossCheckpointAsync()
    {
        // Arrange — a 3-item source table and a freshly-bound foreach executor (instance A).
        const string SourceVariableName = "SourceArray";
        this.SetVariableState("CurrentValue");
        this.State.Set(
            SourceVariableName,
            FormulaValue.NewTable(
                RecordType.Empty(),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(10))),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(20))),
                FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(30)))));

        Foreach model = this.CreateModel(
            displayName: nameof(ForeachStateRestoredAcrossCheckpointAsync),
            items: ValueExpression.Variable(PropertyPath.TopicVariable(SourceVariableName)),
            valueName: "CurrentValue",
            indexName: null);

        ForeachExecutor instanceA = new(model, this.State);

        // Drive instance A through ExecuteAsync (initializes _values/_index) and one TakeNextAsync
        // so that _index advances to 1 and HasValue is true — the state at the point a Question
        // inside the loop body would pause the workflow and trigger a checkpoint.
        await this.ExecuteAsync(instanceA, ForeachExecutor.Steps.Next(instanceA.Id), instanceA.TakeNextAsync);
        Assert.True(instanceA.HasValue, "Instance A should have a current item after the first TakeNextAsync.");

        // Act 1 — instance A persists checkpoint state.
        InMemoryWorkflowContext checkpoint = new();
        await InvokeOnCheckpointingAsync(instanceA, checkpoint);

        // Act 2 — a fresh instance B (simulating cross-process resume) restores from the checkpoint.
        ForeachExecutor instanceB = new(model, this.State);
        await InvokeOnCheckpointRestoredAsync(instanceB, checkpoint);

        // Assert — HasValue carries over so the routing predicate after loopId continues to take
        // the "loop body" edge instead of falling through to the loop continuation.
        Assert.True(instanceB.HasValue, "Restored instance should report HasValue == true at the checkpointed cursor.");

        // Drive iteration 2 and 3 through instance B; both should succeed.
        await instanceB.TakeNextAsync(checkpoint, _: null, CancellationToken.None);
        Assert.True(instanceB.HasValue, "Restored instance should advance to iteration 2 (value=20).");

        await instanceB.TakeNextAsync(checkpoint, _: null, CancellationToken.None);
        Assert.True(instanceB.HasValue, "Restored instance should advance to iteration 3 (value=30).");

        // Driving past the end exits the loop normally.
        await instanceB.TakeNextAsync(checkpoint, _: null, CancellationToken.None);
        Assert.False(instanceB.HasValue, "Restored instance should report HasValue == false after exhausting all items.");
    }

    /// <summary>
    /// When no checkpoint state has been written for the executor (e.g. first run), the restore
    /// hook must be a no-op and leave constructor defaults in place.
    /// </summary>
    [Fact]
    public async Task ForeachRestoreWithNoSavedStateAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");
        Foreach model = this.CreateModel(
            displayName: nameof(ForeachRestoreWithNoSavedStateAsync),
            items: ValueExpression.Literal(DataValue.EmptyTable),
            valueName: "CurrentValue",
            indexName: null);

        ForeachExecutor executor = new(model, this.State);
        InMemoryWorkflowContext emptyContext = new();

        // Act — restoring against an empty context must not throw and must leave the executor
        // in its constructor-default state.
        await InvokeOnCheckpointRestoredAsync(executor, emptyContext);

        // Assert
        Assert.False(executor.HasValue);

        // A subsequent TakeNextAsync (without a prior ExecuteAsync) should report no value
        // because _values is still the empty constructor default.
        await executor.TakeNextAsync(emptyContext, _: null, CancellationToken.None);
        Assert.False(executor.HasValue);
    }

    /// <summary>
    /// Checkpoint/restore around a foreach over an empty source must roundtrip cleanly
    /// (zero-length <c>PortableValue[]</c> snapshot).
    /// </summary>
    [Fact]
    public async Task ForeachStateSurvivesEmptyValuesAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");
        Foreach model = this.CreateModel(
            displayName: nameof(ForeachStateSurvivesEmptyValuesAsync),
            items: ValueExpression.Literal(DataValue.EmptyTable),
            valueName: "CurrentValue",
            indexName: null);

        ForeachExecutor instanceA = new(model, this.State);

        // Run ExecuteAsync (which sets _values = []) followed by one TakeNextAsync (which sets
        // HasValue = false on an empty source).
        await this.ExecuteAsync(instanceA, ForeachExecutor.Steps.Next(instanceA.Id), instanceA.TakeNextAsync);
        Assert.False(instanceA.HasValue);

        // Act — checkpoint and restore into a fresh instance.
        InMemoryWorkflowContext checkpoint = new();
        await InvokeOnCheckpointingAsync(instanceA, checkpoint);

        ForeachExecutor instanceB = new(model, this.State);
        await InvokeOnCheckpointRestoredAsync(instanceB, checkpoint);

        // Assert — restored instance must agree that the source is empty and HasValue is false.
        Assert.False(instanceB.HasValue);

        await instanceB.TakeNextAsync(checkpoint, _: null, CancellationToken.None);
        Assert.False(instanceB.HasValue);
    }

    private void SetVariableState(string valueName, string? indexName = null, FormulaValue? valueState = null)
    {
        this.State.Set(valueName, valueState ?? FormulaValue.New("something"));
        if (indexName is not null)
        {
            this.State.Set(indexName, FormulaValue.New(33));
        }
    }

    private async Task ExecuteTestAsync(
        string displayName,
        ValueExpression items,
        string valueName,
        string? indexName,
        bool expectValue = false)
    {
        // Arrange
        Foreach model = this.CreateModel(displayName, items, valueName, indexName);
        ForeachExecutor action = new(model, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);

        // IsDiscreteAction should be false for Foreach
        VerifyIsDiscrete(action, isDiscrete: false);

        // Verify HasValue state after execution
        Assert.Equal(expectValue, action.HasValue);

        // Verify value was reset at the end
        this.VerifyUndefined(valueName);

        // Verify index was reset at the end if it was used
        if (indexName is not null)
        {
            this.VerifyUndefined(indexName);
        }
    }

    private async Task TakeNextTestAsync(
        string displayName,
        ValueExpression items,
        string valueName,
        string? indexName,
        bool expectValue = true)
    {
        // Arrange
        Foreach model = this.CreateModel(displayName, items, valueName, indexName);
        ForeachExecutor action = new(model, this.State);

        // Act
        await this.ExecuteAsync(action, ForeachExecutor.Steps.Next(action.Id), action.TakeNextAsync);

        // Assert
        VerifyModel(model, action);

        // Verify HasValue state after execution
        Assert.Equal(expectValue, action.HasValue);
    }

    private async Task CompletedTestAsync(
        string displayName,
        string valueName,
        string? indexName)
    {
        // Arrange
        Foreach model = this.CreateModel(displayName, ValueExpression.Literal(DataValue.EmptyTable), valueName, indexName);
        ForeachExecutor action = new(model, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(ForeachExecutor.Steps.End(action.Id), action.CompleteAsync);

        // Assert
        VerifyModel(model, action);
        VerifyCompletionEvent(events);

        // Verify HasValue state after completion
        Assert.False(action.HasValue);

        // Verify value was reset at the end
        this.VerifyUndefined(valueName);

        // Verify index was reset at the end if it was used
        if (indexName is not null)
        {
            this.VerifyUndefined(indexName);
        }
    }

    private Foreach CreateModel(
        string displayName,
        ValueExpression items,
        string valueName,
        string? indexName)
    {
        Foreach.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            Items = items,
            Value = PropertyPath.Create(FormatVariablePath(valueName)),
        };

        if (indexName is not null)
        {
            actionBuilder.Index = PropertyPath.Create(FormatVariablePath(indexName));
        }

        return AssignParent<Foreach>(actionBuilder);
    }

    // Reflection helpers used to invoke the `protected internal` checkpoint hooks on the executor
    // base class from this test project (which is in a different assembly than Microsoft.Agents.AI.Workflows
    // and is not granted InternalsVisibleTo there).
    private static Task InvokeOnCheckpointingAsync(Executor executor, IWorkflowContext context) =>
        InvokeProtectedCheckpointHookAsync(executor, context, methodName: "OnCheckpointingAsync");

    private static Task InvokeOnCheckpointRestoredAsync(Executor executor, IWorkflowContext context) =>
        InvokeProtectedCheckpointHookAsync(executor, context, methodName: "OnCheckpointRestoredAsync");

    private static async Task InvokeProtectedCheckpointHookAsync(Executor executor, IWorkflowContext context, string methodName)
    {
        MethodInfo method = typeof(Executor).GetMethod(
            methodName,
            BindingFlags.Instance | BindingFlags.NonPublic,
            binder: null,
            types: new[] { typeof(IWorkflowContext), typeof(CancellationToken) },
            modifiers: null) ?? throw new InvalidOperationException($"Could not locate {methodName} on Executor.");

        ValueTask invocation = (ValueTask)method.Invoke(executor, new object[] { context, CancellationToken.None })!;
        await invocation;
    }

    /// <summary>
    /// Minimal in-memory <see cref="IWorkflowContext"/> implementation used to drive the
    /// checkpoint/restore overrides on <see cref="ForeachExecutor"/> directly from a unit test.
    /// Records state writes in a (scope, key) dictionary and serves matching reads back. Only the
    /// state-related members are exercised by the checkpoint hooks; the other members are stubbed.
    /// </summary>
    private sealed class InMemoryWorkflowContext : IWorkflowContext
    {
        private readonly Dictionary<(string? scope, string key), object?> _store = [];

        public bool ConcurrentRunsEnabled => false;

        public IReadOnlyDictionary<string, string>? TraceContext => null;

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
        {
            this._store[(scopeName, key)] = value;
            return default;
        }

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
        {
            if (this._store.TryGetValue((scopeName, key), out object? stored) && stored is T typed)
            {
                return new ValueTask<T?>(typed);
            }

            return new ValueTask<T?>(default(T));
        }

        public ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
        {
            if (this._store.TryGetValue((scopeName, key), out object? stored) && stored is T typed)
            {
                return new ValueTask<T>(typed);
            }

            T initial = initialStateFactory();
            this._store[(scopeName, key)] = initial;
            return new ValueTask<T>(initial);
        }

        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
        {
            HashSet<string> keys = new(
                this._store.Keys
                    .Where(slot => string.Equals(slot.scope, scopeName, StringComparison.Ordinal))
                    .Select(slot => slot.key));
            return new ValueTask<HashSet<string>>(keys);
        }

        public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
        {
            foreach ((string? scope, string key) slot in this._store.Keys.Where(slot => string.Equals(slot.scope, scopeName, StringComparison.Ordinal)).ToArray())
            {
                this._store.Remove(slot);
            }

            return default;
        }

        public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default) => default;

        public ValueTask SendMessageAsync(object message, string? targetId, CancellationToken cancellationToken = default) => default;

        public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default) => default;

        public ValueTask RequestHaltAsync() => default;
    }
}
