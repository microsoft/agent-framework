// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

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
        DefaultTemplate template = new(model, "workflow_id");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertDelegate(template.Id, "workflow_id", workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
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
