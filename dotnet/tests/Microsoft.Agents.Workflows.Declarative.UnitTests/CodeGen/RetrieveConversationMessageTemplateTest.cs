// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class RetrieveConversationMessageTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void RetrieveMessageLiteral()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(RetrieveMessageLiteral),
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
        RetrieveConversationMessage model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName),
                conversationExpression,
                messageExpression);

        // Act
        RetrieveConversationMessageTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private RetrieveConversationMessage CreateModel(
        string displayName,
        string variableName,
        StringExpression conversationExpression,
        StringExpression messageExpression)
    {
        RetrieveConversationMessage.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("retrieve_message"),
                DisplayName = this.FormatDisplayName(displayName),
                Message = InitializablePropertyPath.Create(variableName),
                ConversationId = conversationExpression,
                MessageId = messageExpression,
            };

        return actionBuilder.Build();
    }
}
