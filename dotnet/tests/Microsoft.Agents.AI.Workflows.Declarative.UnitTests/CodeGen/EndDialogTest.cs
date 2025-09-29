// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class EndDialogTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void EndDialog()
    {
        // Act, Assert
        this.ExecuteTest(nameof(EndDialog));
    }

    private void ExecuteTest(string displayName)
    {
        // Arrange
        EndDialog model = this.CreateModel(displayName);

        // Act
        DefaultTemplate template = new(model, "workflow_id");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertDelegate(template.Id, "workflow_id", workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
    }

    private EndDialog CreateModel(string displayName)
    {
        EndDialog.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("end_Dialog"),
                DisplayName = this.FormatDisplayName(displayName),
            };

        return actionBuilder.Build();
    }
}
