// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class ClearAllVariablesTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void LiteralEnum()
    {
        // Arrange
        EnumExpression<VariablesToClearWrapper>.Builder expressionBuilder = new(EnumExpression<VariablesToClearWrapper>.Literal(VariablesToClear.AllGlobalVariables));

        // Act, Assert
        this.ExecuteTest(nameof(LiteralEnum), expressionBuilder);
    }

    [Fact]
    public void VariableEnum()
    {
        // Arrange
        EnumExpression<VariablesToClearWrapper>.Builder expressionBuilder = new(EnumExpression<VariablesToClearWrapper>.Variable(PropertyPath.TopicVariable("MyClearEnum")));

        // Act, Assert
        this.ExecuteTest(nameof(VariableEnum), expressionBuilder);
    }

    [Fact]
    public void UnsupportedEnum()
    {
        // Arrange
        EnumExpression<VariablesToClearWrapper>.Builder expressionBuilder = new(EnumExpression<VariablesToClearWrapper>.Literal(VariablesToClear.UserScopedVariables));

        // Act, Assert
        this.ExecuteTest(nameof(UnsupportedEnum), expressionBuilder);
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
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
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
