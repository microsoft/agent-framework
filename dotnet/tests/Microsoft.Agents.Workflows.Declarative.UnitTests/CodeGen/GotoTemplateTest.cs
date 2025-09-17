// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class GotoTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void GotoAction()
    {
        // Act, Assert
        this.ExecuteTest("target_action_id", nameof(GotoAction));
    }

    private void ExecuteTest(
        string targetId,
        string displayName)
    {
        // Arrange
        GotoAction model =
            this.CreateModel(
                targetId,
                displayName);

        // Act
        EmptyTemplate template = new(model, "Go to another action.");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        //Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private GotoAction CreateModel(string targetId, string displayName)
    {
        GotoAction.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("goto_action"),
                DisplayName = this.FormatDisplayName(displayName),
                ActionId = new ActionId(targetId),
            };

        return actionBuilder.Build();
    }
}
