// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class RetrieveConversationMessagesTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void RetrieveMessagesLiteral()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(RetrieveMessagesLiteral),
            "TestVariable",
            StringExpression.Literal("#cid_3"),
            StringExpression.Literal("#mid_43"));
    }

    // %%% TODO: WITH METADATA

    private void ExecuteTest(
        string displayName,
        string variableName,
        StringExpression conversationExpression,
        StringExpression messageExpression)
    {
        // Arrange
        RetrieveConversationMessages model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName),
                conversationExpression,
                messageExpression);

        // Act
        RetrieveConversationMessagesTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private RetrieveConversationMessages CreateModel(
        string displayName,
        string variableName,
        StringExpression conversationExpression,
        StringExpression messageExpression)
    {
        RetrieveConversationMessages.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("retrieve_messages"),
                DisplayName = this.FormatDisplayName(displayName),
                Messages = InitializablePropertyPath.Create(variableName),
                ConversationId = conversationExpression,
                // %%% TODO: ALL PROPERTIES
            };

        return actionBuilder.Build();
    }
}
