// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class SetVariableTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void InitializeLiteralValue()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Literal(new NumberDataValue(420)));

        // Act, Assert
        this.ExecuteTest("TestVariable", expressionBuilder, FormulaValue.New(420), nameof(InitializeLiteralValue));
    }

    [Fact]
    public void InitializeVariable()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Variable(PropertyPath.TopicVariable("MyValue")));

        // Act, Assert
        this.ExecuteTest("TestVariable", expressionBuilder, FormulaValue.New(6), nameof(InitializeVariable));
    }

    [Fact]
    public void InitializeExpression()
    {
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Expression("9 - 3"));

        // Act, Assert
        this.ExecuteTest("TestVariable", expressionBuilder, FormulaValue.New(6), nameof(InitializeExpression));
    }

    private void ExecuteTest(
        string variableName,
        ValueExpression.Builder valueExpression,
        FormulaValue expectedValue,
        string displayName)
    {
        // Arrange
        SetVariable model =
            this.CreateModel(
                FormatVariablePath(variableName),
                valueExpression,
                displayName);

        // Act
        SetVariableTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private SetVariable CreateModel(string variablePath, ValueExpression.Builder valueExpression, string displayName)
    {
        SetVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("set_variable"),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = InitializablePropertyPath.Create(variablePath),
                Value = valueExpression,
            };

        return actionBuilder.Build();
    }
}
