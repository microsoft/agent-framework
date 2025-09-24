// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

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
        this.AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        this.AssertAgentProvider(template.UseAgentProvider, workflowCode);
        this.AssertGeneratedAssignment(model.Variable?.Path, workflowCode);
        Assert.Contains(textValue, workflowCode);
    }

    private SetTextVariable CreateModel(string displayName, string variablePath, string textValue)
    {
        SetTextVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("set_variable"),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = InitializablePropertyPath.Create(variablePath),
                Value = TemplateLine.Parse(textValue),
            };

        return actionBuilder.Build();
    }
}
