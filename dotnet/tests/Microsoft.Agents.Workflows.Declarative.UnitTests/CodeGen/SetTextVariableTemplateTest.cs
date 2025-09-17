// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class SetTextVariableTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void InitializeTemplate()
    {
        // Act, Assert
        this.ExecuteTest("TestVariable", "// %%% WTF", "// %%% WTF", nameof(InitializeTemplate));
    }

    private void ExecuteTest(
        string variableName,
        string textValue,
        string expectedValue,
        string displayName)
    {
        // Arrange
        SetTextVariable model =
            this.CreateModel(
                FormatVariablePath(variableName),
                textValue,
                displayName);

        // Act
        SetTextVariableTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private SetTextVariable CreateModel(string variablePath, string textValue, string displayName)
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
