// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class ContinueLoopTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void ContinueLoop()
    {
        // Act, Assert
        this.ExecuteTest(nameof(ContinueLoop));
    }

    private void ExecuteTest(string displayName)
    {
        // Arrange
        ContinueLoop model = this.CreateModel(displayName);

        // Act
        EmptyTemplate template = new(model, "Continue with the next loop value.");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        //Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private ContinueLoop CreateModel(string displayName)
    {
        ContinueLoop.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("continue_loop"),
                DisplayName = this.FormatDisplayName(displayName),
            };

        return actionBuilder.Build();
    }
}
