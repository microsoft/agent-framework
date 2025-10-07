// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class CopyConversationMessagesTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void CopyConversationMessagesLiteral()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(CopyConversationMessagesLiteral),
            StringExpression.Literal("#conv_dm99"),
            ValueExpression.Variable(PropertyPath.TopicVariable("MyMessages")));
    }

    [Fact]
    public void CopyConversationMessagesVariable()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(CopyConversationMessagesVariable),
            StringExpression.Variable(PropertyPath.TopicVariable("TestConversation")),
            ValueExpression.Variable(PropertyPath.TopicVariable("MyMessages")));
    }

    private void ExecuteTest(
        string displayName,
        StringExpression conversation,
        ValueExpression messages,
        ValueExpression? metadata = null)
    {
        // Arrange
        CopyConversationMessages model =
            this.CreateModel(
                displayName,
                conversation,
                messages);

        // Act
        CopyConversationMessagesTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
    }

    private CopyConversationMessages CreateModel(
        string displayName,
        StringExpression conversation,
        ValueExpression messages,
        ValueExpression? metadata = null)
    {
        CopyConversationMessages.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("copy_messages"),
                DisplayName = this.FormatDisplayName(displayName),
                ConversationId = conversation,
                Messages = messages,
            };

        return actionBuilder.Build();
    }
}
