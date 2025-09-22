// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class CreateConversationTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void CreateConversation()
    {
        // Act, Assert
        this.ExecuteTest(nameof(CreateConversation), "TestVariable");
    }

    // %%% TODO: WITH METADATA

    private void ExecuteTest(string displayName, string variableName)
    {
        // Arrange
        CreateConversation model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName));

        // Act
        CreateConversationTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        this.AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        this.AssertGeneratedAssignment(model.ConversationId?.Path, workflowCode);
    }

    private CreateConversation CreateModel(string displayName, string variablePath)
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
