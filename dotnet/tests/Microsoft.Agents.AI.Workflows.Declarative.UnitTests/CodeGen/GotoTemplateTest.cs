// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

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
        DefaultTemplate template = new(model, "workflow_id");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertDelegate(template.Id, "workflow_id", workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
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
