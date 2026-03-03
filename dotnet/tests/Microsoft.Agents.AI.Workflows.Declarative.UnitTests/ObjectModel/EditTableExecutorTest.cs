// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

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
            value: new RecordDataValue([new("id", new NumberDataValue(7))]));

        // Verify the variable now contains the added record
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultRecord.GetField("id"));
        Assert.Equal(7, idValue.Value);
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

        // Verify the variable now contains the added record
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
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

        // Verify the variable now contains the added record
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
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
            value: new TableDataValue([new RecordDataValue([new("id", new NumberDataValue(3))])]));

        // Verify the variable now contains an empty record
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
        // Empty record should have no fields
        Assert.Empty(resultRecord.Fields);
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

        // Verify the variable now contains an empty record
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
        // Empty record should have no fields
        Assert.Empty(resultRecord.Fields);
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
            value: null);

        // Verify table is cleared
        FormulaValue resultValue = this.State.Get("MyTable");
        Assert.IsType<BlankValue>(resultValue);
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

        // Verify table is blank
        FormulaValue resultValue = this.State.Get("MyTable");
        Assert.IsType<BlankValue>(resultValue);
    }

    [Fact]
    public async Task TakeFirstItemAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 10}, {id: 20}, {id: 30}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeFirstItemAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeFirst,
            value: null);

        // Verify the variable now contains the first record that was taken
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultRecord.GetField("id"));
        Assert.Equal(10, idValue.Value);
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

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeFirstFromEmptyTableAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeFirst,
            value: null);

        // Verify table is still empty (nothing was taken, variable remains unchanged)
        FormulaValue resultValue = this.State.Get("MyTable");
        TableValue resultTable = Assert.IsAssignableFrom<TableValue>(resultValue);
        Assert.Empty(resultTable.Rows);
    }

    [Fact]
    public async Task TakeLastItemAsync()
    {
        // Arrange - Initialize table using Power FX expression
        FormulaValue tableValue = this.State.Engine.Eval("[{id: 10}, {id: 20}, {id: 30}]");
        this.State.Set("MyTable", tableValue);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeLastItemAsync),
            variableName: "MyTable",
            changeType: TableChangeType.TakeLast,
            value: null);

        // Verify the variable now contains the last record that was taken
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultRecord.GetField("id"));
        Assert.Equal(30, idValue.Value);
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

        // Verify variable contains the record that was taken
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultRecord.GetField("id"));
        Assert.Equal(100, idValue.Value);
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

        // Verify variable contains the record that was taken
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultRecord.GetField("id"));
        Assert.Equal(100, idValue.Value);
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

        // Assert - Variable should contain the newly added record
        VerifyModel(model, action);
        FormulaValue resultValue = this.State.Get("MyTable");
        RecordValue resultRecord = Assert.IsAssignableFrom<RecordValue>(resultValue);
        DecimalValue idValue = Assert.IsType<DecimalValue>(resultRecord.GetField("id"));
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
        DataValue? value)
    {
        // Arrange
        EditTable model = this.CreateModel(displayName, variableName, changeType, value);

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
        DataValue? value)
    {
        ValueExpression.Builder? valueExpressionBuilder = value switch
        {
            null => null,
            _ => new ValueExpression.Builder(ValueExpression.Literal(value))
        };

        return this.CreateModel(displayName, variableName, changeType, valueExpressionBuilder);
    }

    private EditTable CreateModel(
        string displayName,
        string variableName,
        TableChangeType changeType,
        ValueExpression valueExpression)
    {
        ValueExpression.Builder valueExpressionBuilder = new(valueExpression);
        return this.CreateModel(displayName, variableName, changeType, valueExpressionBuilder);
    }

    private EditTable CreateModel(
        string displayName,
        string variableName,
        TableChangeType changeType,
        ValueExpression.Builder? valueExpression)
    {
        EditTable.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            ItemsVariable = PropertyPath.Create(FormatVariablePath(variableName)),
            ChangeType = TableChangeTypeWrapper.Get(changeType),
            Value = valueExpression,
        };

        return AssignParent<EditTable>(actionBuilder);
    }
}
