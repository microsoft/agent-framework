// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class BreakLoopTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void BreakLoop()
    {
        // Act, Assert
        this.ExecuteTest(nameof(BreakLoop));
    }

    private void ExecuteTest(string displayName)
    {
        // Arrange
        BreakLoop model = this.CreateModel(displayName);

        // Act
        EmptyTemplate template = new(model, "Break from the current loop.");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        //Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private BreakLoop CreateModel(string displayName)
    {
        BreakLoop.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("break_loop"),
                DisplayName = this.FormatDisplayName(displayName),
            };

        return actionBuilder.Build();
    }
}
