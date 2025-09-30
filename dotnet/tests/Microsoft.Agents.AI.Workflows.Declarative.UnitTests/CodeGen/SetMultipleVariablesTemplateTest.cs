// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class SetMultipleVariablesTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void InitializeMultipleValues()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(InitializeMultipleValues),
            new AssignmentCase("TestVariable1", new ValueExpression.Builder(ValueExpression.Literal(new NumberDataValue(420))), FormulaValue.New(420)),
            new AssignmentCase("TestVariable2", new ValueExpression.Builder(ValueExpression.Variable(PropertyPath.TopicVariable("MyValue"))), FormulaValue.New(6)),
            new AssignmentCase("TestVariable3", new ValueExpression.Builder(ValueExpression.Expression("9 - 3")), FormulaValue.New(6)));
    }

    private void ExecuteTest(string displayName, params AssignmentCase[] assignments)
    {
        // Arrange
        SetMultipleVariables model =
            this.CreateModel(
                displayName,
                assignments);

        // Act
        SetMultipleVariablesTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        foreach (AssignmentCase assignment in assignments)
        {
            AssertGeneratedAssignment(PropertyPath.TopicVariable(assignment.Path), workflowCode);
        }
    }

    private SetMultipleVariables CreateModel(string displayName, params AssignmentCase[] assignments)
    {
        SetMultipleVariables.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("set_multiple"),
                DisplayName = this.FormatDisplayName(displayName),
            };

        foreach (AssignmentCase assignment in assignments)
        {
            actionBuilder.Assignments.Add(
                new VariableAssignment.Builder()
                {
                    Variable = PropertyPath.Create(FormatVariablePath(assignment.Path)),
                    Value = assignment.Expression,
                });
        }

        return actionBuilder.Build();
    }

    private sealed record AssignmentCase(string Path, ValueExpression.Builder Expression, FormulaValue Expected);
}
