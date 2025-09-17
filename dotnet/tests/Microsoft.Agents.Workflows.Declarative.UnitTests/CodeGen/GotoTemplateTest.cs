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
        this.ExecuteTest(nameof(GotoAction), "target_action_id");
    }

    private void ExecuteTest(string displayName, string targetId)
    {
        // Arrange
        GotoAction model = this.CreateModel(displayName, targetId);

        // Act
        EmptyTemplate template = new(model, "Go to another action.");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        //Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private GotoAction CreateModel(string displayName, string targetId)
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
