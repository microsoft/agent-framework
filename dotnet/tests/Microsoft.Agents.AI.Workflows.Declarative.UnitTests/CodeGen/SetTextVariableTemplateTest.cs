// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class SetTextVariableTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void InitializeTemplate()
    {
        // Act, Assert
        this.ExecuteTest(nameof(InitializeTemplate), "TestVariable", "Value: {OtherVar}");
    }

    private void ExecuteTest(
        string displayName,
        string variableName,
        string textValue)
    {
        // Arrange
        SetTextVariable model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName),
                textValue);

        // Act
        SetTextVariableTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        AssertGeneratedAssignment(model.Variable?.Path, workflowCode);
        Assert.Contains(textValue, workflowCode);
    }

    private SetTextVariable CreateModel(string displayName, string variablePath, string textValue)
    {
        SetTextVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("set_variable"),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = PropertyPath.Create(variablePath),
                Value = TemplateLine.Parse(textValue),
            };

        return actionBuilder.Build();
    }
}
