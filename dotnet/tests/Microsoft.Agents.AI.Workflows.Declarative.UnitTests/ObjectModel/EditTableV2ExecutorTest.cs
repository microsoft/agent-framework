// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="EditTableV2Executor"/>.
/// </summary>
public sealed class EditTableV2ExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void InvalidModel_NullItemsVariable()
    {
        // Arrange
        EditTableV2 model = new EditTableV2.Builder
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(nameof(InvalidModel_NullItemsVariable)),
            ItemsVariable = null,
            ChangeType = new AddItemOperation.Builder
            {
                Value = new ValueExpression.Builder(ValueExpression.Literal(new StringDataValue("test")))
            }.Build()
        }.Build();

        // Act, Assert
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => new EditTableV2Executor(model, this.State));
        Assert.Contains("required", exception.Message, System.StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task InvalidModel_VariableNotTable()
    {
        // Arrange
        const string variableName = "NotATable";
        this.State.Set(variableName, FormulaValue.New("I am a string"));
        this.State.Bind();

        EditTableV2 model = this.CreateModel(
            nameof(InvalidModel_VariableNotTable),
            variableName,
            new AddItemOperation.Builder
            {
                Value = new ValueExpression.Builder(ValueExpression.Literal(new StringDataValue("test")))
            }.Build());

        EditTableV2Executor action = new(model, this.State);

        // Act & Assert
        await Assert.ThrowsAsync<DeclarativeActionException>(async () => await this.ExecuteAsync(action));
    }

    [Fact]
    public async Task AddItemOperation_WithSingleFieldRecordAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(AddItemOperation_WithSingleFieldRecordAsync),
            variableName: "TestTable",
            changeType: this.CreateAddItemOperation(new RecordDataValue.Builder
            {
                Properties =
                {
                    ["Name"] = new StringDataValue("John")
                }
            }.Build()),
            setupAction: (variableName) =>
            {
                // Create an empty table with single field
                RecordType recordType = RecordType.Empty().Add("Name", FormulaType.String);
                TableValue tableValue = FormulaValue.NewTable(recordType);
                this.State.Set(variableName, tableValue);
                this.State.Bind();
            },
            verifyAction: (variableName) =>
            {
                FormulaValue value = this.State.Get(variableName);
                Assert.IsAssignableFrom<RecordValue>(value);
                RecordValue recordValue = (RecordValue)value;
                Assert.Equal("John", recordValue.GetField("Name").ToObject());
            });
    }

    [Fact]
    public async Task AddItemOperation_WithScalarValueAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(AddItemOperation_WithScalarValueAsync),
            variableName: "TestTable",
            changeType: this.CreateAddItemOperation(new StringDataValue("TestValue")),
            setupAction: (variableName) =>
            {
                // Create an empty table with single field
                RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
                TableValue tableValue = FormulaValue.NewTable(recordType);
                this.State.Set(variableName, tableValue);
                this.State.Bind();
            },
            verifyAction: (variableName) =>
            {
                FormulaValue value = this.State.Get(variableName);
                Assert.IsAssignableFrom<RecordValue>(value);
                RecordValue recordValue = (RecordValue)value;
                Assert.Equal("TestValue", recordValue.GetField("Value").ToObject());
            });
    }

    [Fact]
    public async Task ClearItemsOperationAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ClearItemsOperationAsync),
            variableName: "TestTable",
            changeType: new ClearItemsOperation.Builder().Build(),
            setupAction: (variableName) =>
            {
                // Create a table with some items
                RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
                RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
                RecordValue record2 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item2")));
                TableValue tableValue = FormulaValue.NewTable(recordType, record1, record2);
                this.State.Set(variableName, tableValue);
                this.State.Bind();
            },
            verifyAction: (variableName) =>
            {
                FormulaValue value = this.State.Get(variableName);
                Assert.IsAssignableFrom<BlankValue>(value);
            });
    }

    [Fact]
    public async Task RemoveItemOperationAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(RemoveItemOperationAsync),
            variableName: "TestTable",
            changeType: this.CreateRemoveItemOperation("Item1"),
            setupAction: (variableName) =>
            {
                // Create a table with some items
                RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
                RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
                RecordValue record2 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item2")));
                TableValue tableValue = FormulaValue.NewTable(recordType, record1, record2);
                this.State.Set(variableName, tableValue);
                this.State.Bind();
            },
            verifyAction: (variableName) =>
            {
                FormulaValue value = this.State.Get(variableName);
                Assert.IsAssignableFrom<BlankValue>(value);
            });
    }

    [Fact]
    public async Task TakeLastItemOperation_WithItemsAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeLastItemOperation_WithItemsAsync),
            variableName: "TestTable",
            changeType: new TakeLastItemOperation.Builder().Build(),
            setupAction: (variableName) =>
            {
                // Create a table with some items
                RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
                RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
                RecordValue record2 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item2")));
                RecordValue record3 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item3")));
                TableValue tableValue = FormulaValue.NewTable(recordType, record1, record2, record3);
                this.State.Set(variableName, tableValue);
                this.State.Bind();
            },
            verifyAction: (variableName) =>
            {
                FormulaValue value = this.State.Get(variableName);
                Assert.IsAssignableFrom<RecordValue>(value);
                RecordValue recordValue = (RecordValue)value;
                Assert.Equal("Item3", recordValue.GetField("Value").ToObject());
            });
    }

    [Fact]
    public async Task TakeLastItemOperation_EmptyTableAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeLastItemOperation_EmptyTableAsync),
            variableName: "TestTable",
            changeType: new TakeLastItemOperation.Builder().Build(),
            setupAction: (variableName) =>
            {
                // Create an empty table
                RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
                TableValue tableValue = FormulaValue.NewTable(recordType);
                this.State.Set(variableName, tableValue);
                this.State.Bind();
            },
            verifyAction: (variableName) =>
            {
                FormulaValue value = this.State.Get(variableName);
                // When table is empty, no assignment happens, so the variable should still be the table
                Assert.IsAssignableFrom<TableValue>(value);
            });
    }

    [Fact]
    public async Task TakeFirstItemOperation_WithItemsAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeFirstItemOperation_WithItemsAsync),
            variableName: "TestTable",
            changeType: new TakeFirstItemOperation.Builder().Build(),
            setupAction: (variableName) =>
            {
                // Create a table with some items
                RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
                RecordValue record1 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item1")));
                RecordValue record2 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item2")));
                RecordValue record3 = FormulaValue.NewRecordFromFields(recordType, new NamedValue("Value", FormulaValue.New("Item3")));
                TableValue tableValue = FormulaValue.NewTable(recordType, record1, record2, record3);
                this.State.Set(variableName, tableValue);
                this.State.Bind();
            },
            verifyAction: (variableName) =>
            {
                FormulaValue value = this.State.Get(variableName);
                Assert.IsAssignableFrom<RecordValue>(value);
                RecordValue recordValue = (RecordValue)value;
                Assert.Equal("Item1", recordValue.GetField("Value").ToObject());
            });
    }

    [Fact]
    public async Task TakeFirstItemOperation_EmptyTableAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(TakeFirstItemOperation_EmptyTableAsync),
            variableName: "TestTable",
            changeType: new TakeFirstItemOperation.Builder().Build(),
            setupAction: (variableName) =>
            {
                // Create an empty table
                RecordType recordType = RecordType.Empty().Add("Value", FormulaType.String);
                TableValue tableValue = FormulaValue.NewTable(recordType);
                this.State.Set(variableName, tableValue);
                this.State.Bind();
            },
            verifyAction: (variableName) =>
            {
                FormulaValue value = this.State.Get(variableName);
                // When table is empty, no assignment happens, so the variable should still be the table
                Assert.IsAssignableFrom<TableValue>(value);
            });
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        EditTableOperation changeType,
        System.Action<string> setupAction,
        System.Action<string> verifyAction)
    {
        // Arrange
        setupAction(variableName);

        EditTableV2 model = this.CreateModel(displayName, variableName, changeType);

        // Act
        EditTableV2Executor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        verifyAction(variableName);
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
        this.State.Set("_RemoveItems", tableToRemove);
        this.State.Bind();

        return new RemoveItemOperation.Builder
        {
            Value = new ValueExpression.Builder(ValueExpression.Variable(PropertyPath.TopicVariable("_RemoveItems")))
        }.Build();
    }
}
