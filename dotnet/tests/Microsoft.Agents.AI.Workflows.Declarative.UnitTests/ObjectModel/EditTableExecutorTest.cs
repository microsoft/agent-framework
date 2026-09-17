// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="EditTableExecutor"/>.
/// </summary>
public sealed class EditTableExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void InvalidModelNullItemsVariable() =>
        // Arrange, Act, Assert
        Assert.Throws<DeclarativeModelException>(() => new EditTableExecutor(new EditTable(), this.State));

    [Fact]
    public async Task AddItemToTableAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 3}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(AddItemToTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.Add,
            value: new RecordDataValue([new("id", new NumberDataValue(7))]),
            resultVariableName: "Result");

        // Verify the variable remains a table containing the added record
        FormulaValue resultValue = this.State.Get("MyTable");
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resultValue);
        Assert.Equal(2, resultTable.Rows.Count());
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultTable.Rows.Last().Value.GetField("id"));
        Assert.Equal(7, idValue.Value);
        Assert.Equal(7, Assert.IsType<DecimalValue>(
            Assert.IsAssignableFrom<RecordValue>(this.State.Get("Result")).GetField("id")).Value);
    }

    [Fact]
    public async Task ConsecutiveAddsPreserveTableAsync()
    {
        // Arrange
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 1}]");
        this.State.Set("MyTable", tableValue);

        EditTable firstAdd = this.CreateModel(
            nameof(ConsecutiveAddsPreserveTableAsync),
            "MyTable",
            TableChangeType.Add,
            new RecordDataValue([new("id", new NumberDataValue(2))]));
        EditTable secondAdd = this.CreateModel(
            nameof(ConsecutiveAddsPreserveTableAsync),
            "MyTable",
            TableChangeType.Add,
            new RecordDataValue([new("id", new NumberDataValue(3))]));

        // Act
        await this.ExecuteAsync(new EditTableExecutor(firstAdd, this.State));
        await this.ExecuteAsync(new EditTableExecutor(secondAdd, this.State));

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        decimal[] ids = resultTable.Rows
            .Select(row => Assert.IsType<DecimalValue>(row.Value.GetField("id")).Value)
            .ToArray();
        Assert.Equal([1, 2, 3], ids);
    }

    [Fact]
    public async Task AddItemWithMultipleFieldsAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 1, name: \"First\"}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(AddItemWithMultipleFieldsAsync),
            variableName: "MyTable",
            changeType: TableChangeType.Add,
            value: new RecordDataValue([
                new("id", new NumberDataValue(2)),
                new("name", new StringDataValue("Second"))
            ]));

        // Verify the variable remains a table containing the added record
        FormulaValue resultValue = this.State.Get("MyTable");
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resultValue);
        Assert.Equal(2, resultTable.Rows.Count());
        RecordValue resultRecord = resultTable.Rows.Last().Value;
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultRecord.GetField("id"));
        Assert.Equal(2, idValue.Value);
        StringValue nameValue = Assert.IsType<StringValue>(resultRecord.GetField("name"));
        Assert.Equal("Second", nameValue.Value);
    }

    [Fact]
    public async Task AddItemToEmptyTableAsync()
    {
        // Arrange - Initialize empty table using Power FX expression with schema
        FormulaValue tableValue = this.State.Engine.Eval("Table({id: 1})");
        TableValue table = Assert.IsAssignableFrom<TableValue>(tableValue);
        // Clear the table to make it empty but preserve schema
        await table.ClearAsync(CancellationToken.None);
        this.State.Set("MyTable", table);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(AddItemToEmptyTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.Add,
            value: new RecordDataValue([new("id", new NumberDataValue(1))]));

        // Verify the variable remains a table containing the added record
        FormulaValue resultValue = this.State.Get("MyTable");
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resultValue);
        RecordValue resultRecord = Assert.Single(resultTable.Rows).Value;
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultRecord.GetField("id"));
        Assert.Equal(1, idValue.Value);
    }

    [Fact]
    public async Task RemoveItemFromTableAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 3}, {id: 7}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(RemoveItemFromTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.Remove,
            value: new TableDataValue([new RecordDataValue([new("id", new NumberDataValue(3))])]),
            resultVariableName: "Result");

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        DecimalValue idValue = Assert.IsType<DecimalValue>(Assert.Single(resultTable.Rows).Value.GetField("id"));
        Assert.Equal(7, idValue.Value);
        Assert.Empty(Assert.IsAssignableFrom<RecordValue>(this.State.Get("Result")).Fields);
    }

    [Fact]
    public async Task RemoveMultipleItemsFromTableAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 1}, {id: 2}, {id: 3}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(RemoveMultipleItemsFromTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.Remove,
            value: new TableDataValue([
                new RecordDataValue([new("id", new NumberDataValue(1))]),
                new RecordDataValue([new("id", new NumberDataValue(3))])
            ]));

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        DecimalValue idValue = Assert.IsType<DecimalValue>(Assert.Single(resultTable.Rows).Value.GetField("id"));
        Assert.Equal(2, idValue.Value);
    }

    [Fact]
    public async Task RemoveAllThenRestoreThenAddPreservesTableAsync()
    {
        // Arrange
        this.State.Set("MyTable", this.State.Engine.Eval("[{id: 1}, {id: 2}]"));
        EditTable removeAction = this.CreateModel(
            nameof(RemoveAllThenRestoreThenAddPreservesTableAsync),
            "MyTable",
            TableChangeType.Remove,
            new TableDataValue([
                new RecordDataValue([new("id", new NumberDataValue(1))]),
                new RecordDataValue([new("id", new NumberDataValue(2))])
            ]));
        EditTable addAction = this.CreateModel(
            nameof(RemoveAllThenRestoreThenAddPreservesTableAsync),
            "MyTable",
            TableChangeType.Add,
            new RecordDataValue([new("id", new NumberDataValue(3))]));

        // Act
        await this.ExecuteAsync(new EditTableExecutor(removeAction, this.State));
        this.State.Set("MyTable", new PortableValue(this.State.Get("MyTable").AsPortable()).ToFormula());
        await this.ExecuteAsync(new EditTableExecutor(addAction, this.State));

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        Assert.Equal(3, Assert.IsType<DecimalValue>(Assert.Single(resultTable.Rows).Value.GetField("id")).Value);
    }

    [Fact]
    public async Task ClearTableAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 1}, {id: 2}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ClearTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.Clear,
            value: null,
            resultVariableName: "Result");

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        Assert.Empty(resultTable.Rows);
        Assert.Equal(FormulaType.Decimal, resultTable.Type.GetFieldType("id"));
        Assert.IsType<BlankValue>(this.State.Get("Result"));
    }

    [Fact]
    public async Task ClearEmptyTableAsync()
    {
        // Arrange - Initialize empty table using Power FX expression with schema
        FormulaValue tableValue = this.State.Engine.Eval("Table({id: 1})");
        TableValue table = Assert.IsAssignableFrom<TableValue>(tableValue);
        // Clear the table to make it empty but preserve schema
        await table.ClearAsync(CancellationToken.None);
        this.State.Set("MyTable", table);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ClearEmptyTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.Clear,
            value: null);

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        Assert.Empty(resultTable.Rows);
        Assert.Equal(FormulaType.Decimal, resultTable.Type.GetFieldType("id"));
    }

    [Fact]
    public async Task ClearThenRestoreThenAddPreservesTableAsync()
    {
        // Arrange
        this.State.Set("MyTable", this.State.Engine.Eval("[{id: 1}, {id: 2}]"));
        EditTable clearAction = this.CreateModel(
            nameof(ClearThenRestoreThenAddPreservesTableAsync),
            "MyTable",
            TableChangeType.Clear,
            value: null);
        EditTable addAction = this.CreateModel(
            nameof(ClearThenRestoreThenAddPreservesTableAsync),
            "MyTable",
            TableChangeType.Add,
            new RecordDataValue([new("id", new NumberDataValue(3))]));

        // Act
        await this.ExecuteAsync(new EditTableExecutor(clearAction, this.State));
        this.State.Set("MyTable", new PortableValue(this.State.Get("MyTable").AsPortable()).ToFormula());
        await this.ExecuteAsync(new EditTableExecutor(addAction, this.State));

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        DecimalValue idValue = Assert.IsType<DecimalValue>(Assert.Single(resultTable.Rows).Value.GetField("id"));
        Assert.Equal(3, idValue.Value);
    }

    [Fact]
    public async Task ClearThenCheckpointResumeThenAddPreservesTableAsync()
    {
        // Arrange
        EditTable clearModel = this.CreateModel(
            nameof(ClearThenCheckpointResumeThenAddPreservesTableAsync),
            "MyTable",
            TableChangeType.Clear,
            value: null);
        EditTable addModel = this.CreateModel(
            nameof(ClearThenCheckpointResumeThenAddPreservesTableAsync),
            "MyTable",
            TableChangeType.Add,
            new RecordDataValue([new("id", new NumberDataValue(3))]));

        WorkflowFormulaState firstState = new(RecalcEngineFactory.Create());
        firstState.Set("MyTable", firstState.Engine.Eval("[{id: 1}, {id: 2}]"));
        Workflow firstWorkflow = BuildWorkflow(firstState);

        InMemoryJsonStore store = new();
        CheckpointManager checkpointManager = CheckpointManager.CreateJson(store, DeclarativeWorkflowJsonOptions.Default);
        List<CheckpointInfo> checkpoints = [];

        await using (StreamingRun run = await InProcessExecution.RunStreamingAsync(firstWorkflow, firstState, checkpointManager))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } checkpoint })
                {
                    checkpoints.Add(checkpoint);
                }
            }
        }
        Assert.True(checkpoints.Count >= 3);

        WorkflowFormulaState resumedState = new(RecalcEngineFactory.Create());
        Workflow resumedWorkflow = BuildWorkflow(resumedState);

        // Act
        await using (StreamingRun run = await InProcessExecution.ResumeStreamingAsync(resumedWorkflow, checkpoints[^2], checkpointManager))
        {
            await foreach (WorkflowEvent _ in run.WatchStreamAsync())
            {
            }
        }

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resumedState.Get("MyTable"));
        Assert.Equal(3, Assert.IsType<DecimalValue>(Assert.Single(resultTable.Rows).Value.GetField("id")).Value);

        Workflow BuildWorkflow(WorkflowFormulaState state)
        {
            TestWorkflowExecutor root = new();
            EditTableExecutor clearAction = new(clearModel, state);
            EditTableExecutor addAction = new(addModel, state);
            return
                new WorkflowBuilder(root)
                    .AddEdge(root, clearAction)
                    .AddEdge(clearAction, addAction)
                    .Build();
        }
    }

    [Fact]
    public async Task TakeFirstItemAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 10}, {id: 20}, {id: 30}]");
        this.State.Set("MyTable", tableValue);

        EditTable model = this.CreateModel(
            nameof(TakeFirstItemAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeFirst,
            value: null,
            resultVariableName: "TakenItem");

        // Act
        await this.ExecuteAsync(new EditTableExecutor(model, this.State));

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        decimal[] ids = resultTable.Rows
            .Select(row => Assert.IsType<DecimalValue>(row.Value.GetField("id")).Value)
            .ToArray();
        Assert.Equal([20, 30], ids);

        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(this.State.Get("TakenItem"));
        Assert.Equal(10, Assert.IsType<DecimalValue>(resultRecord.GetField("id")).Value);
    }

    [Fact]
    public async Task TakeFirstFromEmptyTableAsync()
    {
        // Arrange - Initialize empty table using Power FX expression with schema
        FormulaValue tableValue = this.State.Engine.Eval("Table({id: 1})");
        TableValue table = Assert.IsAssignableFrom<TableValue>(tableValue);
        // Clear the table to make it empty but preserve schema
        await table.ClearAsync(CancellationToken.None);
        this.State.Set("MyTable", table);
        this.State.Set("TakenItem", FormulaValue.NewRecordFromFields(new NamedValue("id", FormulaValue.New(99))));

        EditTable model = this.CreateModel(
            nameof(TakeFirstFromEmptyTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeFirst,
            value: null,
            resultVariableName: "TakenItem");

        // Act
        await this.ExecuteAsync(new EditTableExecutor(model, this.State));

        // Verify table is still empty (nothing was taken, variable remains unchanged)
        FormulaValue resultValue = this.State.Get("MyTable");
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resultValue);
        Assert.Empty(resultTable.Rows);
        Assert.IsType<BlankValue>(this.State.Get("TakenItem"));
    }

    [Fact]
    public async Task TakeLastItemAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 10}, {id: 20}, {id: 30}]");
        this.State.Set("MyTable", tableValue);

        EditTable model = this.CreateModel(
            nameof(TakeLastItemAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeLast,
            value: null,
            resultVariableName: "TakenItem");

        // Act
        await this.ExecuteAsync(new EditTableExecutor(model, this.State));

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        decimal[] ids = resultTable.Rows
            .Select(row => Assert.IsType<DecimalValue>(row.Value.GetField("id")).Value)
            .ToArray();
        Assert.Equal([10, 20], ids);

        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(this.State.Get("TakenItem"));
        Assert.Equal(30, Assert.IsType<DecimalValue>(resultRecord.GetField("id")).Value);
    }

    [Fact]
    public async Task TakeLastFromEmptyTableAsync()
    {
        // Arrange - Initialize empty table using Power FX expression with schema
        FormulaValue tableValue = this.State.Engine.Eval("Table({id: 1})");
        TableValue table = Assert.IsAssignableFrom<TableValue>(tableValue);
        // Clear the table to make it empty but preserve schema
        await table.ClearAsync(CancellationToken.None);
        this.State.Set("MyTable", table);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeLastFromEmptyTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeLast,
            value: null);

        // Verify table is still empty (nothing was taken, variable remains unchanged)
        FormulaValue resultValue = this.State.Get("MyTable");
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resultValue);
        Assert.Empty(resultTable.Rows);
    }

    [Fact]
    public async Task TakeFirstFromSingleItemTableAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 100}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeFirstFromSingleItemTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeFirst,
            value: null);

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        Assert.Empty(resultTable.Rows);
    }

    [Fact]
    public async Task TakeLastFromSingleItemTableAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 100}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeLastFromSingleItemTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeLast,
            value: null);

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        Assert.Empty(resultTable.Rows);
    }

    [Fact]
    public async Task TakeFirstThenAddPreservesTableAsync()
    {
        // Arrange
        this.State.Set("MyTable", this.State.Engine.Eval("[{id: 1}, {id: 2}]"));
        EditTable takeAction = this.CreateModel(
            nameof(TakeFirstThenAddPreservesTableAsync),
            "MyTable",
            TableChangeType.TakeFirst,
            value: null,
            resultVariableName: "TakenItem");
        EditTable addAction = this.CreateModel(
            nameof(TakeFirstThenAddPreservesTableAsync),
            "MyTable",
            TableChangeType.Add,
            new RecordDataValue([new("id", new NumberDataValue(3))]));

        // Act
        await this.ExecuteAsync(new EditTableExecutor(takeAction, this.State));
        await this.ExecuteAsync(new EditTableExecutor(addAction, this.State));

        // Assert
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(this.State.Get("MyTable"));
        decimal[] ids = resultTable.Rows
            .Select(row => Assert.IsType<DecimalValue>(row.Value.GetField("id")).Value)
            .ToArray();
        Assert.Equal([2, 3], ids);
        Assert.Equal(1, Assert.IsType<DecimalValue>(
            Assert.IsAssignableFrom<RecordValue>(this.State.Get("TakenItem")).GetField("id")).Value);
    }

    [Fact]
    public async Task ErrorWhenVariableIsNotTableAsync()
    {
        // Arrange
        this.State.Set("NotATable", FormulaValue.New("This is a string, not a table"));

        EditTable model = this.CreateModel(
            nameof(ErrorWhenVariableIsNotTableAsync),
            "NotATable",
            TableChangeType.Add,
            new RecordDataValue([new("id", new NumberDataValue(1))]));

        // Act
        EditTableExecutor action = new(model, this.State);

        // Assert - Should throw an exception for non-table variable
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(
            async () => await this.ExecuteAsync(action));
        Assert.NotNull(exception);
    }

    [Fact]
    public async Task AddWithExpressionAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 5}]");
        this.State.Set("MyTable", tableValue);
        this.State.Set("NewId", FormulaValue.New(10));

        EditTable model = this.CreateModel(
            nameof(AddWithExpressionAsync),
            "MyTable",
            TableChangeType.Add,
            ValueExpression.Expression("{id: Local.NewId}"));

        // Act
        EditTableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert - Variable should remain a table containing the newly added record
        VerifyModel(model, action);
        FormulaValue resultValue = this.State.Get("MyTable");
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resultValue);
        Assert.Equal(2, resultTable.Rows.Count());
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultTable.Rows.Last().Value.GetField("id"));
        Assert.Equal(10, idValue.Value);
    }

    [Fact]
    public async Task RemoveWithNonTableValueAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 1}, {id: 2}]");
        this.State.Set("MyTable", tableValue);

        // Try to remove using a non-table value (should not throw, just not remove anything)
        EditTable model = this.CreateModel(
            nameof(RemoveWithNonTableValueAsync),
            "MyTable",
            TableChangeType.Remove,
            new RecordDataValue([new("id", new NumberDataValue(1))]));

        // Act
        EditTableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert - table should remain unchanged since value is not a TableDataValue
        VerifyModel(model, action);
        FormulaValue resultValue = this.State.Get("MyTable");
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resultValue);
        Assert.Equal(2, resultTable.Rows.Count());
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        TableChangeType changeType,
        DataValue? value,
        string? resultVariableName = null)
    {
        // Arrange
        EditTable model = this.CreateModel(displayName, variableName, changeType, value, resultVariableName);

        // Act
        EditTableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
    }

    private EditTable CreateModel(
        string displayName,
        string variableName,
        TableChangeType changeType,
        DataValue? value,
        string? resultVariableName = null)
    {
        ValueExpression.Builder? valueExpressionBuilder = value switch
        {
            null => null,
            _ => new ValueExpression.Builder(ValueExpression.Literal(value))
        };

        return this.CreateModel(displayName, variableName, changeType, valueExpressionBuilder, resultVariableName);
    }

    private EditTable CreateModel(
        string displayName,
        string variableName,
        TableChangeType changeType,
        ValueExpression valueExpression,
        string? resultVariableName = null)
    {
        ValueExpression.Builder valueExpressionBuilder = new(valueExpression);
        return this.CreateModel(displayName, variableName, changeType, valueExpressionBuilder, resultVariableName);
    }

    private EditTable CreateModel(
        string displayName,
        string variableName,
        TableChangeType changeType,
        ValueExpression.Builder? valueExpression,
        string? resultVariableName = null)
    {
        EditTable.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            ItemsVariable = PropertyPath.Create(FormatVariablePath(variableName)),
            ChangeType = TableChangeTypeWrapper.Get(changeType),
            Value = valueExpression,
        };
        if (resultVariableName is not null)
        {
            actionBuilder.ResultVariable = PropertyPath.Create(FormatVariablePath(resultVariableName));
        }

        return AssignParent<EditTable>(actionBuilder);
    }

    private sealed class InMemoryJsonStore : JsonCheckpointStore
    {
        private readonly Dictionary<CheckpointInfo, JsonElement> _store = [];

        public override ValueTask<CheckpointInfo> CreateCheckpointAsync(
            string sessionId, JsonElement value, CheckpointInfo? parent = null)
        {
            CheckpointInfo key = new(sessionId, Guid.NewGuid().ToString("N"));
            this._store[key] = value;
            return new(key);
        }

        public override ValueTask<JsonElement> RetrieveCheckpointAsync(string sessionId, CheckpointInfo key) =>
            new(this._store[key]);

        public override ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(
            string sessionId, CheckpointInfo? withParent = null) =>
            new(this._store.Keys.Where(key => key.SessionId == sessionId));
    }
}
