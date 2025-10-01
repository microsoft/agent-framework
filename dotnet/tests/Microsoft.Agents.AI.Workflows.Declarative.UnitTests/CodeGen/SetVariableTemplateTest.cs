// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class SetVariableTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void InitializeLiteralValue()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Literal(new NumberDataValue(420)));

        // Act, Assert
        this.ExecuteTest(nameof(InitializeLiteralValue), "TestVariable", expressionBuilder, FormulaValue.New(420));
    }

    [Fact]
    public void InitializeVariable()
    {
        // Arrange
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Variable(PropertyPath.TopicVariable("MyValue")));

        // Act, Assert
        this.ExecuteTest(nameof(InitializeVariable), "TestVariable", expressionBuilder, FormulaValue.New(6));
    }

    [Fact]
    public void InitializeExpression()
    {
        ValueExpression.Builder expressionBuilder = new(ValueExpression.Expression("9 - 3"));

        // Act, Assert
        this.ExecuteTest(nameof(InitializeExpression), "TestVariable", expressionBuilder, FormulaValue.New(6));
    }

    private void ExecuteTest(
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

        // Act
        SetVariableTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        AssertGeneratedAssignment(model.Variable?.Path, workflowCode);
    }

    private SetVariable CreateModel(string displayName, string variablePath, ValueExpression.Builder valueExpression)
    {
        SetVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("set_variable"),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = PropertyPath.Create(variablePath),
                Value = valueExpression,
            };

        return actionBuilder.Build();
    }
}
