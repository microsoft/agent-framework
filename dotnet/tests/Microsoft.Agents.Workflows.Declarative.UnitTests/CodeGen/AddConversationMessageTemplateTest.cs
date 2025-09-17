// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class AddConversationMessageTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void AddConversationMessage()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(AddConversationMessage),
            "TestVariable",
            conversation: StringExpression.Literal("#rev_9"),
            content:
            [
                new AddConversationMessageContent.Builder()
                {
                    Type = AgentMessageContentType.Text,
                    Value = TemplateLine.Parse("Hello! How can I help you today?"),
                },
            ]);
    }

    // %%% TODO: WITH METADATA, ROLE

    private void ExecuteTest(
        string displayName,
        string variableName,
        StringExpression conversation,
        IEnumerable<AddConversationMessageContent.Builder> content,
        EnumExpression<AgentMessageRoleWrapper>.Builder? role = null,
        ObjectExpression<RecordDataValue>.Builder? metadata = null)
    {
        // Arrange
        AddConversationMessage model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName),
                conversation,
                content,
                role,
                metadata);

        // Act
        AddConversationMessageTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        Assert.Contains(variableName, workflowCode); // %%% MORE VALIDATION
    }

    private AddConversationMessage CreateModel(
        string displayName,
        string variablePath,
        StringExpression conversation,
        IEnumerable<AddConversationMessageContent.Builder> contents,
        EnumExpression<AgentMessageRoleWrapper>.Builder? role,
        ObjectExpression<RecordDataValue>.Builder? metadata)
    {
        AddConversationMessage.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("add_message"),
                DisplayName = this.FormatDisplayName(displayName),
                ConversationId = conversation,
                Message = InitializablePropertyPath.Create(variablePath),
                Role = role,
                Metadata = metadata,
            };

        foreach (AddConversationMessageContent.Builder content in contents)
        {
            actionBuilder.Content.Add(content);
        }

        return actionBuilder.Build();
    }
}
