// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class ClearAllVariablesTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void InitializeLiteralValue()
    {
        // Arrange
        EnumExpression<VariablesToClearWrapper>.Builder expressionBuilder = new(EnumExpression<VariablesToClearWrapper>.Literal(VariablesToClear.AllGlobalVariables));

        // Act, Assert
        this.ExecuteTest(nameof(InitializeLiteralValue), expressionBuilder);
    }

    [Fact]
    public void InitializeVariable()
    {
        // Arrange
        EnumExpression<VariablesToClearWrapper>.Builder expressionBuilder = new(EnumExpression<VariablesToClearWrapper>.Variable(PropertyPath.TopicVariable("MyClearEnum")));

        // Act, Assert
        this.ExecuteTest(nameof(InitializeVariable), expressionBuilder);
    }

    private void ExecuteTest(
        string displayName,
        EnumExpression<VariablesToClearWrapper>.Builder variablesExpression)
    {
        // Arrange
        ClearAllVariables model =
            this.CreateModel(
                displayName,
                variablesExpression);

        // Act
        ClearAllVariablesTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        //Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private ClearAllVariables CreateModel(
        string displayName,
        EnumExpression<VariablesToClearWrapper>.Builder variablesExpression)
    {
        ClearAllVariables.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("set_variable"),
                DisplayName = this.FormatDisplayName(displayName),
                Variables = variablesExpression,
            };

        return actionBuilder.Build();
    }
}
