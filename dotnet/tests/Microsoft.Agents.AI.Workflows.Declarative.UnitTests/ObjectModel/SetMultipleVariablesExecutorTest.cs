// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="SetMultipleVariablesExecutor"/>.
/// </summary>
public sealed class SetMultipleVariablesExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task SetMultipleVariablesAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetMultipleVariablesAsync),
            assignments: [
                new AssignmentCase("Variable1", new NumberDataValue(42), FormulaValue.New(42)),
                new AssignmentCase("Variable2", new StringDataValue("Test"), FormulaValue.New("Test")),
                new AssignmentCase("Variable3", new BooleanDataValue(true), FormulaValue.New(true))
            ]);
    }

    [Fact]
    public async Task SetMultipleVariablesWithExpressionsAsync()
    {
        // Arrange
        this.State.Set("SourceNumber", FormulaValue.New(10));
        this.State.Set("SourceText", FormulaValue.New("Hello"));
        this.State.Bind();

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetMultipleVariablesWithExpressionsAsync),
            assignments: [
                new AssignmentCase("CalcVariable", ValueExpression.Expression("Local.SourceNumber * 2"), FormulaValue.New(20)),
                new AssignmentCase("ConcatVariable", ValueExpression.Expression(@"Concatenate(Local.SourceText, "" World"")"), FormulaValue.New("Hello World")),
                new AssignmentCase("BoolVariable", ValueExpression.Expression("Local.SourceNumber > 5"), FormulaValue.New(true))
            ]);
    }

    [Fact]
    public async Task SetMultipleVariablesWithVariableReferencesAsync()
    {
        // Arrange
        this.State.Set("Source1", FormulaValue.New(123));
        this.State.Set("Source2", FormulaValue.New("Reference"));
        this.State.Bind();

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetMultipleVariablesWithVariableReferencesAsync),
            assignments: [
                new AssignmentCase("Target1", ValueExpression.Variable(PropertyPath.TopicVariable("Source1")), FormulaValue.New(123)),
                new AssignmentCase("Target2", ValueExpression.Variable(PropertyPath.TopicVariable("Source2")), FormulaValue.New("Reference"))
            ]);
    }

    [Fact]
    public async Task SetMultipleVariablesWithNullValuesAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetMultipleVariablesWithNullValuesAsync),
            assignments: [
                new AssignmentCase("NullVar1", null, FormulaValue.NewBlank()),
                new AssignmentCase("NormalVar", new StringDataValue("NotNull"), FormulaValue.New("NotNull")),
                new AssignmentCase("NullVar2", null, FormulaValue.NewBlank())
            ]);
    }

    [Fact]
    public async Task SetMultipleVariablesUpdateExistingAsync()
    {
        // Arrange
        this.State.Set("ExistingVar1", FormulaValue.New(999));
        this.State.Set("ExistingVar2", FormulaValue.New("OldValue"));

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(SetMultipleVariablesUpdateExistingAsync),
            assignments: [
                new AssignmentCase("ExistingVar1", new NumberDataValue(111), FormulaValue.New(111)),
                new AssignmentCase("ExistingVar2", new StringDataValue("NewValue"), FormulaValue.New("NewValue")),
                new AssignmentCase("NewVar", new BooleanDataValue(false), FormulaValue.New(false))
            ]);
    }

    [Fact]
    public async Task SetMultipleVariablesEmptyAssignmentsAsync()
    {
        // Arrange
        SetMultipleVariables model = this.CreateModel(nameof(SetMultipleVariablesEmptyAssignmentsAsync), []);

        // Arrange, Act, Assert
        Assert.Throws<DeclarativeModelException>(() =>
        {
            // Empty variables assignment should fail RequiredProperties validation.
            _ = new SetMultipleVariablesExecutor(model, this.State);
        });
    }

    private async Task ExecuteTestAsync(string displayName, AssignmentCase[] assignments)
    {
        // Arrange
        SetMultipleVariables model = this.CreateModel(displayName, assignments);

        // Act
        SetMultipleVariablesExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        foreach (AssignmentCase assignment in assignments)
        {
            this.VerifyState(assignment.VariableName, assignment.ExpectedValue);
        }
    }

    private SetMultipleVariables CreateModel(string displayName, AssignmentCase[] assignments)
    {
        SetMultipleVariables.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
        };

        foreach (AssignmentCase assignment in assignments)
        {
            ValueExpression.Builder? valueExpressionBuilder = assignment.ValueExpression switch
            {
                null => null,
                DataValue dataValue => new ValueExpression.Builder(ValueExpression.Literal(dataValue)),
                ValueExpression valueExpression => new ValueExpression.Builder(valueExpression),
                _ => throw new System.ArgumentException($"Unsupported value type: {assignment.ValueExpression?.GetType().Name}")
            };

            actionBuilder.Assignments.Add(new VariableAssignment.Builder()
            {
                Variable = PropertyPath.Create(FormatVariablePath(assignment.VariableName)),
                Value = valueExpressionBuilder,
            });
        }

        return AssignParent<SetMultipleVariables>(actionBuilder);
    }

    private sealed record AssignmentCase(string VariableName, object? ValueExpression, FormulaValue ExpectedValue);
}
