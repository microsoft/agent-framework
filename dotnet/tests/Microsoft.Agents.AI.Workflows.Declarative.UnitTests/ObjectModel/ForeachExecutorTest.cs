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
}
