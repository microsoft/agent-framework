// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class SetVariableTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public async Task InitializeLiteralValue()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Literal(new NumberDataValue(420)));

        // Act, Assert
        await this.ExecuteTest("TestVariable", expressionBuilder, FormulaValue.New(420), nameof(InitializeLiteralValue));
    }

    [Fact]
    public async Task InitializeVariable()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Variable(PropertyPath.TopicVariable("MyValue")));

        // Act, Assert
        await this.ExecuteTest("TestVariable", expressionBuilder, FormulaValue.New(6), nameof(InitializeVariable));
    }

    [Fact]
    public async Task InitializeExpression()
    {
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Expression("9 - 3"));

        // Act, Assert
        await this.ExecuteTest("TestVariable", expressionBuilder, FormulaValue.New(6), nameof(InitializeVariable));
    }

    private async Task ExecuteTest(
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
        string text = this.Execute(() => template.TransformText());

        // Assert
        this.Output.WriteLine(text); // %%% TODO: VALIDATE
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
