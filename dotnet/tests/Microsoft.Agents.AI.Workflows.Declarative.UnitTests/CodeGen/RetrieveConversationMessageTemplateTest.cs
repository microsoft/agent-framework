// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class RetrieveConversationMessageTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void RetrieveConversationVariable()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(RetrieveConversationVariable),
            "TestVariable",
            StringExpression.Variable(PropertyPath.TopicVariable("TestConversation")),
            StringExpression.Literal("#mid_43"));
    }
    [Fact]
    public void RetrieveMessageVariable()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(RetrieveMessageVariable),
            "TestVariable",
            StringExpression.Literal("#cid_3"),
            StringExpression.Variable(PropertyPath.TopicVariable("TestMessage")));
    }

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
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        AssertGeneratedAssignment(model.Message?.Path, workflowCode);
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
                Message = PropertyPath.Create(variableName),
                ConversationId = conversationExpression,
                MessageId = messageExpression,
            };

        return actionBuilder.Build();
    }
}
