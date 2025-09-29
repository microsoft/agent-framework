// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class EndConversationTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void EndConversation()
    {
        // Act, Assert
        this.ExecuteTest(nameof(EndConversation));
    }

    private void ExecuteTest(string displayName)
    {
        // Arrange
        EndConversation model = this.CreateModel(displayName);

        // Act
        DefaultTemplate template = new(model, "workflow_id");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertDelegate(template.Id, "workflow_id", workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
    }

    private EndConversation CreateModel(string displayName)
    {
        EndConversation.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("end_conversation"),
                DisplayName = this.FormatDisplayName(displayName),
            };

        return actionBuilder.Build();
    }
}
