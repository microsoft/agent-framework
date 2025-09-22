// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

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
        DefaultTemplate template = new(model, "Ends the conversation");
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        //Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
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
