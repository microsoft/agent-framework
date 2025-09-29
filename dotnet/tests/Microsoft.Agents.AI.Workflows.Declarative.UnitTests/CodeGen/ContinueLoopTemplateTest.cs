// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

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
        DefaultTemplate template = new(model, "workflow_id");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertDelegate(template.Id, "workflow_id", workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
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
