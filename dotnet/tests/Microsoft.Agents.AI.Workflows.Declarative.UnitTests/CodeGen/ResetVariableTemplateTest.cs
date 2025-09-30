// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class ResetVariableTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void ResetVariable()
    {
        // Act, Assert
        this.ExecuteTest(nameof(ResetVariable), "TestVariable");
    }

    private void ExecuteTest(string displayName, string variableName)
    {
        // Arrange
        ResetVariable model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName));

        // Act
        ResetVariableTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
    }

    private ResetVariable CreateModel(string displayName, string variablePath)
    {
        ResetVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("set_variable"),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = PropertyPath.Create(variablePath)
            };

        return actionBuilder.Build();
    }
}
