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
        // Arrange, Act & Assert
        Assert.Throws<DeclarativeModelException>(() => new ForeachExecutor(new Foreach(), this.State));

    [Fact]
    public void NamingConvention()
    {
        // Arrange
        const string TestId = "test_action_123";

        // Act
        string startStep = ForeachExecutor.Steps.Start(TestId);
        string nextStep = ForeachExecutor.Steps.Next(TestId);
        string endStep = ForeachExecutor.Steps.End(TestId);

        // Assert
        Assert.Equal($"{TestId}_{nameof(ForeachExecutor.Steps.Start)}", startStep);
        Assert.Equal($"{TestId}_{nameof(ForeachExecutor.Steps.Next)}", nextStep);
        Assert.Equal($"{TestId}_{nameof(ForeachExecutor.Steps.End)}", endStep);
    }

    [Fact]
    public async Task ForeachWithSingleValueAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithSingleValueAsync),
            items: ValueExpression.Literal(new NumberDataValue(42)),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachWithStringValueAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithStringValueAsync),
            items: ValueExpression.Literal(new StringDataValue("Test")),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachWithTableValueAsync()
    {
        // Arrange
        TableDataValue tableValue = DataValue.TableFromRecords(
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(1))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(2))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new NumberDataValue(3))));

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithTableValueAsync),
            items: ValueExpression.Literal(tableValue),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachWithIndexAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue", "CurrentIndex");
        TableDataValue tableValue = DataValue.TableFromRecords(
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new StringDataValue("A"))),
            DataValue.RecordFromFields(new KeyValuePair<string, DataValue>("item", new StringDataValue("B"))));

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithIndexAsync),
            items: ValueExpression.Literal(tableValue),
            valueName: "CurrentValue",
            indexName: "CurrentIndex");
    }

    [Fact]
    public async Task ForeachWithEmptyTableAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithEmptyTableAsync),
            items: ValueExpression.Literal(DataValue.EmptyTable),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachWithExpressionAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");
        this.State.Set("SourceArray", FormulaValue.NewTable(
            RecordType.Empty(),
            FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(10))),
            FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(20))),
            FormulaValue.NewRecordFromFields(new NamedValue("value", FormulaValue.New(30)))));

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ForeachWithExpressionAsync),
            items: ValueExpression.Variable(PropertyPath.TopicVariable("SourceArray")),
            valueName: "CurrentValue",
            indexName: null);
    }

    [Fact]
    public async Task ForeachCompletedWithoutIndexAsync()
    {
        // Arrange
        this.SetVariableState("CurrentValue");

        // Act & Assert
        await this.CompletedTestAsync(
            displayName: nameof(ForeachCompletedWithoutIndexAsync),
            items: ValueExpression.Literal(DataValue.EmptyTable),
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
            items: ValueExpression.Literal(DataValue.EmptyTable),
            valueName: "CurrentValue",
            indexName: "CurrentIndex");
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

        // Act
        ForeachExecutor action = new(model, this.State);
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);

        // IsDiscreteAction should be false for Foreach
        Assert.Equal(
            false,
            action.GetType()
            .BaseType?
            .GetProperty("IsDiscreteAction", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
            .GetValue(action));

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

    private async Task CompletedTestAsync(
        string displayName,
        ValueExpression items,
        string valueName,
        string? indexName)
    {
        // Arrange
        Foreach model = this.CreateModel(displayName, items, valueName, indexName);
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
}
