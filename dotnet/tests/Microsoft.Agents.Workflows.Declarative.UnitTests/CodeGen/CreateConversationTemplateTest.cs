// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class CreateConversationTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void CreateConversation()
    {
        // Act, Assert
        this.ExecuteTest("TestVariable", nameof(CreateConversation));
    }

    // %%% TODO: WITH METADATA

    private void ExecuteTest(
        string variableName,
        string displayName)
    {
        // Arrange
        CreateConversation model =
            this.CreateModel(
                FormatVariablePath(variableName),
                displayName);

        // Act
        CreateConversationTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private CreateConversation CreateModel(string variablePath, string displayName)
    {
        CreateConversation.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("create_conversation"),
                DisplayName = this.FormatDisplayName(displayName),
                ConversationId = InitializablePropertyPath.Create(variablePath),
            };

        return actionBuilder.Build();
    }
}
