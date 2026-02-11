// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="ForeachExecutor"/>.
/// </summary>
public sealed class ForeachExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void InvalidModel() =>
        // Arrange, Act, Assert
        Assert.Throws<DeclarativeModelException>(() => new ForeachExecutor(new Foreach(), this.State));

    [Fact]
    public async Task ForeachWithSingleValueAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithSingleValueAsync),
            items: ValueExpression.Literal(new NumberDataValue(42)),
            valueName: "CurrentValue",
            indexName: null,
            expectedValues: [FormulaValue.New(42)],
            expectIterations: 1);
    }

    [Fact]
    public async Task ForeachWithStringValueAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithStringValueAsync),
            items: ValueExpression.Literal(new StringDataValue("Test")),
            valueName: "CurrentValue",
            indexName: null,
            expectedValues: [FormulaValue.New("Test")],
            expectIterations: 1);
    }

    [Fact]
    public async Task ForeachWithTableValueAsync()
    {
        // Arrange
        TableDataValue tableValue = DataValue.TableFromRecords(
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(1))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(2))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(3))));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithTableValueAsync),
            items: ValueExpression.Literal(tableValue),
            valueName: "CurrentValue",
            indexName: null,
            expectedValues: [FormulaValue.New(1), FormulaValue.New(2), FormulaValue.New(3)],
            expectIterations: 3);
    }

    [Fact]
    public async Task ForeachWithIndexAsync()
    {
        // Arrange
        TableDataValue tableValue = DataValue.TableFromRecords(
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new StringDataValue("A"))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new StringDataValue("B"))));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithIndexAsync),
            items: ValueExpression.Literal(tableValue),
            valueName: "CurrentValue",
            indexName: "CurrentIndex",
            expectedValues: [FormulaValue.New("A"), FormulaValue.New("B")],
            expectIterations: 2);
    }

    [Fact]
    public async Task ForeachWithEmptyTableAsync()
    {
        // Arrange
        TableDataValue emptyTable = DataValue.TableFromRecords();

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithEmptyTableAsync),
            items: ValueExpression.Literal(emptyTable),
            valueName: "CurrentValue",
            indexName: null,
            expectedValues: [],
            expectIterations: 0);
    }

    [Fact]
    public async Task ForeachWithExpressionAsync()
    {
        // Arrange
        this.State.Set("SourceArray", FormulaValue.NewTable(
            RecordType.Empty(),
            FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(10))),
            FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(20))),
            FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(30)))));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithExpressionAsync),
            items: ValueExpression.Variable(PropertyPath.TopicVariable("SourceArray")),
            valueName: "CurrentValue",
            indexName: null,
            expectedValues: [FormulaValue.New(10), FormulaValue.New(20), FormulaValue.New(30)],
            expectIterations: 3);
    }

    [Fact]
    public async Task ForeachWithoutIndexAsync()
    {
        // Arrange
        TableDataValue tableValue = DataValue.TableFromRecords(
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new BooleanDataValue(true))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new BooleanDataValue(false))));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithoutIndexAsync),
            items: ValueExpression.Literal(tableValue),
            valueName: "CurrentValue",
            indexName: null,
            expectedValues: [FormulaValue.New(true), FormulaValue.New(false)],
            expectIterations: 2);
    }

    [Fact]
    public void StepsNamingConvention() // %%% TODO: Needed ???
    {
        // Arrange
        const string TestId = "test_action_123";

        // Act
        string startStep = ForeachExecutor.Steps.Start(TestId);
        string nextStep = ForeachExecutor.Steps.Next(TestId);
        string endStep = ForeachExecutor.Steps.End(TestId);

        // Assert
        Assert.Equal($"{TestId}_Start", startStep);
        Assert.Equal($"{TestId}_Next", nextStep);
        Assert.Equal($"{TestId}_End", endStep);
    }

    [Fact]
    public async Task HasValuePropertyTransitionsAsync()
    {
        // Arrange
        TableDataValue tableValue = DataValue.TableFromRecords(
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(1))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(2))));

        Foreach model = this.CreateModel(
            displayName: nameof(HasValuePropertyTransitionsAsync),
            items: ValueExpression.Literal(tableValue),
            valueName: "CurrentValue",
            indexName: null);

        ForeachExecutor executor = new(model, this.State);

        // Act & Assert - Before execution
        Assert.False(executor.HasValue);

        // Execute to initialize
        await this.ExecuteAsync(executor);

        // After execution, HasValue should be set based on TakeNextAsync logic
        // The executor should have processed the iterations
        Assert.False(executor.HasValue); // After all iterations, HasValue is false
    }

    [Fact]
    public async Task IsDiscreteActionPropertyAsync()
    {
        // Arrange
        Foreach model = this.CreateModel(
            displayName: nameof(IsDiscreteActionPropertyAsync),
            items: ValueExpression.Literal(new NumberDataValue(1)),
            valueName: "CurrentValue",
            indexName: null);

        // Act
        ForeachExecutor executor = new(model, this.State);

        // Assert - IsDiscreteAction should be false for Foreach
        Assert.Equal(
            false,
            executor.GetType()
            .BaseType?
            .GetProperty("IsDiscreteAction", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
            .GetValue(executor));
    }

    private async Task ExecuteTestAsync(
        string displayName,
        ValueExpression items,
        string valueName,
        string? indexName,
        FormulaValue[] expectedValues,
        int expectIterations)
    {
        // Arrange
        Foreach model = this.CreateModel(displayName, items, valueName, indexName);

        // Act
        ForeachExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);

        // Verify HasValue state after execution
        if (expectIterations == 0)
        {
            Assert.False(action.HasValue);
        }
        else
        {
            // After complete execution, HasValue should be false (no more items)
            Assert.False(action.HasValue);
        }

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
}
