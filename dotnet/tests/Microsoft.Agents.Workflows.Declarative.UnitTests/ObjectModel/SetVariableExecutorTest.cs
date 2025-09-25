// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="SetVariableExecutor"/>.
/// </summary>
public sealed class SetVariableExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void InvalidModel() =>
        // Arrange, Act, Assert
        Assert.Throws<DeclarativeModelException>(() => new SetVariableExecutor(new SetVariable(), this.State));

    [Fact]
    public async Task SetNumericValueAsync() =>
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetNumericValueAsync),
            variableName: "TestVariable",
            variableValue: new NumberDataValue(42),
            expectedValue: FormulaValue.New(42));

    [Fact]
    public async Task SetStringValueAsync() =>
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetStringValueAsync),
            variableName: "TestVariable",
            variableValue: new StringDataValue("Text"),
            expectedValue: FormulaValue.New("Text"));

    [Fact]
    public async Task SetBooleanValueAsync() =>
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetBooleanValueAsync),
            variableName: "TestVariable",
            variableValue: new BooleanDataValue(true),
            expectedValue: FormulaValue.New(true));

    [Fact]
    public async Task SetBooleanExpressionAsync()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Expression("true || false"));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetBooleanExpressionAsync),
            variableName: "TestVariable",
            valueExpression: expressionBuilder,
            expectedValue: FormulaValue.New(true));
    }

    [Fact]
    public async Task SetNumberExpressionAsync()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Expression("9 - 3"));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetBooleanExpressionAsync),
            variableName: "TestVariable",
            valueExpression: expressionBuilder,
            expectedValue: FormulaValue.New(6));
    }

    [Fact]
    public async Task SetStringExpressionAsync()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Expression(@"Concatenate(""A"", ""B"", ""C"")"));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetBooleanExpressionAsync),
            variableName: "TestVariable",
            valueExpression: expressionBuilder,
            expectedValue: FormulaValue.New("ABC"));
    }

    [Fact]
    public async Task SetBooleanVariableAsync()
    {
        // Arrange
        this.State.Set("Source", FormulaValue.New(true));
        this.State.Bind();

        ValueExpression.Builder expressionBuilder = new(ValueExpression.Variable(PropertyPath.TopicVariable("Source")));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetBooleanExpressionAsync),
            variableName: "TestVariable",
            valueExpression: expressionBuilder,
            expectedValue: FormulaValue.New(true));
    }

    [Fact]
    public async Task SetNumberVariableAsync()
    {
        // Arrange
        this.State.Set("Source", FormulaValue.New(321));
        this.State.Bind();

        ValueExpression.Builder expressionBuilder = new(ValueExpression.Variable(PropertyPath.TopicVariable("Source")));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetBooleanExpressionAsync),
            variableName: "TestVariable",
            valueExpression: expressionBuilder,
            expectedValue: FormulaValue.New(321));
    }

    [Fact]
    public async Task SetStringVariableAsync()
    {
        // Arrange
        this.State.Set("Source", FormulaValue.New("Test"));
        this.State.Bind();

        ValueExpression.Builder expressionBuilder = new(ValueExpression.Variable(PropertyPath.TopicVariable("Source")));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetBooleanExpressionAsync),
            variableName: "TestVariable",
            valueExpression: expressionBuilder,
            expectedValue: FormulaValue.New("Test"));
    }

    [Fact]
    public async Task UpdateExistingValueAsync()
    {
        // Arrange
        this.State.Set("VarA", FormulaValue.New(33));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(UpdateExistingValueAsync),
            variableName: "VarA",
            variableValue: new NumberDataValue(42),
            expectedValue: FormulaValue.New(42));
    }

    private Task ExecuteTestAsync(
        string displayName,
        string variableName,
        DataValue variableValue,
        FormulaValue expectedValue)
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Literal(variableValue));

        // Act & Assert
        return this.ExecuteTestAsync(displayName, variableName, expressionBuilder, expectedValue);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        ValueExpression.Builder valueExpression,
        FormulaValue expectedValue)
    {
        // Arrange
        SetVariable model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName),
                valueExpression);

        this.State.Set(variableName, FormulaValue.New(33));

        // Act
        SetVariableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState(variableName, expectedValue);
    }

    private SetVariable CreateModel(string displayName, string variablePath, ValueExpression.Builder valueExpression)
    {
        SetVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = InitializablePropertyPath.Create(variablePath),
                Value = valueExpression,
            };

        return AssignParent<SetVariable>(actionBuilder);
    }
}
