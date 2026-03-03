// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="EditTableV2Executor"/>.
/// </summary>
public sealed class EditTableV2ExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void InvalidModelNullItemsVariable()
    {
        // Arrange
        EditTableV2 model = new EditTableV2.Builder
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(nameof(InvalidModelNullItemsVariable)),
            ItemsVariable = null,
            ChangeType = new AddItemOperation.Builder
            {
                Value = new ValueExpression.Builder(ValueExpression.Literal(new StringDataValue("test")))
            }.Build()
        }.Build();

        // Act, Assert
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => new EditTableV2Executor(model, this.State));
        Assert.Contains("required", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task InvalidModelVariableNotTableAsync()
    {
        // Arrange
        this.State.Set("NotATable", FormulaValue.New("I am a string"));

        EditTableV2 model = this.CreateModel(
            nameof(InvalidModelVariableNotTableAsync),
            "NotATable",
            new AddItemOperation.Builder
            {
                Value = new ValueExpression.Builder(ValueExpression.Literal(new StringDataValue("test")))
            }.Build());

        EditTableV2Executor action = new(model, this.State);

        // Act & Assert
        await Assert.ThrowsAsync<DeclarativeActionException>(async () => await this.ExecuteAsync(action));
    }

    [Fact]
    public async Task InvalidModelAddItemOperationNullValueAsync()
    {
        // Arrange
        EditTableV2 model = new EditTableV2.Builder
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(nameof(InvalidModelAddItemOperationNullValueAsync)),
            ItemsVariable = PropertyPath.Create(FormatVariablePath("TestTable")),
            ChangeType = new AddItemOperation.Builder
            {
                Value = null
            }.Build()
        }.Build();

        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        TableValue tableValue = FormulaValue.NewTable(recordType);
        this.State.Set("TestTable", tableValue);

        // Act, Assert
        EditTableV2Executor action = new(model, this.State);
        await Assert.ThrowsAsync<DeclarativeActionException>(async () => await this.ExecuteAsync(action));
    }

    [Fact]
    public async Task InvalidModelRemoveItemOperationNullValueAsync()
    {
        // Arrange
        EditTableV2 model = new EditTableV2.Builder
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(nameof(InvalidModelRemoveItemOperationNullValueAsync)),
            ItemsVariable = PropertyPath.Create(FormatVariablePath("TestTable")),
            ChangeType = new RemoveItemOperation.Builder
            {
                Value = null
            }.Build()
        }.Build();

        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        TableValue tableValue = FormulaValue.NewTable(recordType);
        this.State.Set("TestTable", tableValue);

        // Act, Assert
        EditTableV2Executor action = new(model, this.State);
        await Assert.ThrowsAsync<DeclarativeActionException>(async () => await this.ExecuteAsync(action));
    }

    [Fact]
    public async Task RemoveItemOperationNonTableValueAsync()
    {
        // Arrange
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
        TableValue tableValue = FormulaValue.NewTable(recordType, record1);
        this.State.Set("TestTable", tableValue);

        // Set a string value instead of a table for removal
        this.State.Set("RemoveItems", FormulaValue.New("NotATable"));

        EditTableV2 model = new EditTableV2.Builder
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(nameof(RemoveItemOperationNonTableValueAsync)),
            ItemsVariable = PropertyPath.Create(FormatVariablePath("TestTable")),
            ChangeType = new RemoveItemOperation.Builder
            {
                Value = new ValueExpression.Builder(ValueExpression.Variable(PropertyPath.TopicVariable("RemoveItems")))
            }.Build()
        }.Build();

        // Act
        EditTableV2Executor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert: When the remove value is not a table, no removal occurs, so the table should be unchanged
        FormulaValue value = this.State.Get("TestTable");
        Assert.IsAssignableFrom<TableValue>(value);
        TableValue resultTable = (TableValue)value;
        Assert.Single(resultTable.Rows);
    }

    [Fact]
    public async Task AddItemOperationWithSingleFieldRecordAsync()
    {
        // Arrange: Create an empty table with single field
        RecordType recordType = RecordType.Empty().Add("Name", FormulaType.String);
        TableValue tableValue = FormulaValue.NewTable(recordType);
        this.State.Set("TestTable", tableValue);

        // Arrange, Act, Assert
        await this.ExecuteTestAsync<RecordValue>(
            displayName: nameof(AddItemOperationWithSingleFieldRecordAsync),
            variableName: "TestTable",
            changeType: this.CreateAddItemOperation(new RecordDataValue.Builder
            {
                Properties =
                {
                    ["Name"] = new StringDataValue("John")
                }
            }.Build()),
            verifyAction: (variableName, recordValue) =>
                Assert.Equal("John", recordValue.GetField("Name").ToObject())
            );
    }

    [Fact]
    public async Task AddItemOperationWithScalarValueAsync()
    {
        // Arrange: Create an empty table with single field
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        TableValue tableValue = FormulaValue.NewTable(recordType);
        this.State.Set("TestTable", tableValue);

        // Act & Assert
        await this.ExecuteTestAsync<RecordValue>(
            displayName: nameof(AddItemOperationWithScalarValueAsync),
            variableName: "TestTable",
            changeType: this.CreateAddItemOperation(new StringDataValue("TestValue")),
            verifyAction: (variableName, recordValue) =>
                Assert.Equal("TestValue", recordValue.GetField("Value").ToObject())
            );
    }

    [Fact]
    public async Task ClearItemsOperationAsync()
    {
        // Arrange: Create a table with some items
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
        RecordValue record2 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item2")));
        TableValue tableValue = FormulaValue.NewTable(recordType, record1, record2);
        this.State.Set("TestTable", tableValue);

        // Act & Assert
        await this.ExecuteTestAsync<BlankValue>(
            displayName: nameof(ClearItemsOperationAsync),
            variableName: "TestTable",
            changeType: new ClearItemsOperation.Builder().Build());
    }

    [Fact]
    public async Task RemoveItemOperationAsync()
    {
        // Arrange: Create a table with some items
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
        RecordValue record2 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item2")));
        TableValue tableValue = FormulaValue.NewTable(recordType, record1, record2);
        this.State.Set("TestTable", tableValue);

        // Act & Assert
        await this.ExecuteTestAsync<BlankValue>(
            displayName: nameof(RemoveItemOperationAsync),
            variableName: "TestTable",
            changeType: this.CreateRemoveItemOperation("Item1"));
    }

    [Fact]
    public async Task TakeLastItemOperationWithItemsAsync()
    {
        // Arrange: Create a table with some items
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
        RecordValue record2 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item2")));
        RecordValue record3 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item3")));
        TableValue tableValue = FormulaValue.NewTable(recordType, record1, record2, record3);
        this.State.Set("TestTable", tableValue);

        // Arrange, Act, Assert
        await this.ExecuteTestAsync<RecordValue>(
            displayName: nameof(TakeLastItemOperationWithItemsAsync),
            variableName: "TestTable",
            changeType: new TakeLastItemOperation.Builder().Build(),
            verifyAction: (variableName, recordValue) =>
                Assert.Equal("Item3", recordValue.GetField("Value").ToObject())
            );
    }

    [Fact]
    public async Task TakeLastItemOperationEmptyTableAsync()
    {
        // Arrange: Create an empty table
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        TableValue tableValue = FormulaValue.NewTable(recordType);
        this.State.Set("TestTable", tableValue);

        // Arrange, Act, Assert
        await this.ExecuteTestAsync<TableValue>(
            displayName: nameof(TakeLastItemOperationEmptyTableAsync),
            variableName: "TestTable",
            changeType: new TakeLastItemOperation.Builder().Build());
    }

    [Fact]
    public async Task TakeFirstItemOperationWithItemsAsync()
    {
        // Arrange: Create a table with some items
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
        RecordValue record2 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item2")));
        RecordValue record3 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item3")));
        TableValue tableValue = FormulaValue.NewTable(recordType, record1, record2, record3);
        this.State.Set("TestTable", tableValue);

        // Act & Assert
        await this.ExecuteTestAsync<RecordValue>(
            displayName: nameof(TakeFirstItemOperationWithItemsAsync),
            variableName: "TestTable",
            changeType: new TakeFirstItemOperation.Builder().Build(),
            verifyAction: (variableName, recordValue) =>
                Assert.Equal("Item1", recordValue.GetField("Value").ToObject())
            );
    }

    [Fact]
    public async Task TakeFirstItemOperationEmptyTableAsync()
    {
        // Arrange: Create an empty table
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        TableValue tableValue = FormulaValue.NewTable(recordType);
        this.State.Set("TestTable", tableValue);

        // Act & Assert
        await this.ExecuteTestAsync<TableValue>(
            displayName: nameof(TakeFirstItemOperationEmptyTableAsync),
            variableName: "TestTable",
            changeType: new TakeFirstItemOperation.Builder().Build());
    }

    private async Task ExecuteTestAsync<TValue>(
        string displayName,
        string variableName,
        EditTableOperation changeType,
        Action<string, TValue>? verifyAction = null) where TValue : FormulaValue
    {
        // Arrange
        EditTableV2 model = this.CreateModel(displayName, variableName, changeType);

        EditTableV2Executor action = new(model, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        FormulaValue value = this.State.Get(variableName);
        TValue typedValue = Assert.IsAssignableFrom<TValue>(value);
        verifyAction?.Invoke(variableName, typedValue);
    }

    private EditTableV2 CreateModel(string displayName, string variableName, EditTableOperation changeType)
    {
        EditTableV2.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            ItemsVariable = PropertyPath.Create(FormatVariablePath(variableName)),
            ChangeType = changeType
        };

        return AssignParent<EditTableV2>(actionBuilder);
    }

    private AddItemOperation CreateAddItemOperation(DataValue value)
    {
        return new AddItemOperation.Builder
        {
            Value = new ValueExpression.Builder(ValueExpression.Literal(value))
        }.Build();
    }

    private RemoveItemOperation CreateRemoveItemOperation(string itemValue)
    {
        // Create a table with the item to remove
        RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
        RecordValue recordToRemove = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New(itemValue)));
        TableValue tableToRemove = FormulaValue.NewTable(recordType, recordToRemove);

        // Store in state for expression evaluation
        this.State.Set("RemoveItems", tableToRemove);
        this.State.Bind();

        return new RemoveItemOperation.Builder
        {
            Value = new ValueExpression.Builder(ValueExpression.Variable(PropertyPath.TopicVariable("RemoveItems")))
        }.Build();
    }
}
