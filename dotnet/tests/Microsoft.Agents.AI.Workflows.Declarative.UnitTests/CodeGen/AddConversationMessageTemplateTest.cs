// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class AddConversationMessageTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void NoRole()
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

    [Fact]
    public void WithRole()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(AddConversationMessage),
            "TestVariable",
            conversation: StringExpression.Variable(PropertyPath.Create("System.ConversationId")),
            role: AgentMessageRoleWrapper.Get(AgentMessageRole.Agent),
            content:
            [
                new AddConversationMessageContent.Builder()
                {
                    Type = AgentMessageContentType.Text,
                    Value = TemplateLine.Parse("Hello! How can I help you today?"),
                },
            ]);
    }

    [Fact]
    public void WithMetadataLiteral()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(AddConversationMessage),
            "TestVariable",
            conversation: StringExpression.Variable(PropertyPath.Create("System.Conversation.Id")),
            role: AgentMessageRoleWrapper.Get(AgentMessageRole.Agent),
            metadata: ObjectExpression<RecordDataValue>.Literal(
                new RecordDataValue(
                    new Dictionary<string, DataValue>
                    {
                        { "key1", StringDataValue.Create("value1") },
                        { "key2", NumberDataValue.Create(42) },
                    }.ToImmutableDictionary())),
            content:
            [
                new AddConversationMessageContent.Builder()
                {
                    Type = AgentMessageContentType.Text,
                    Value = TemplateLine.Parse("Hello! How can I help you today?"),
                },
            ]);
    }

    [Fact]
    public void WithMetadataVariable()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(AddConversationMessage),
            "TestVariable",
            conversation: StringExpression.Literal("#rev_9"),
            role: AgentMessageRoleWrapper.Get(AgentMessageRole.Agent),
            metadata: ObjectExpression<RecordDataValue>.Variable(PropertyPath.TopicVariable("MyMetadata")),
            content:
            [
                new AddConversationMessageContent.Builder()
                {
                    Type = AgentMessageContentType.Text,
                    Value = TemplateLine.Parse("Hello! How can I help you today?"),
                },
            ]);
    }

    private void ExecuteTest(
        string displayName,
        string variableName,
        StringExpression conversation,
        IEnumerable<AddConversationMessageContent.Builder> content,
        AgentMessageRoleWrapper? role = null,
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
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        AssertGeneratedAssignment(model.Message?.Path, workflowCode);
    }

    private AddConversationMessage CreateModel(
        string displayName,
        string variablePath,
        StringExpression conversation,
        IEnumerable<AddConversationMessageContent.Builder> contents,
        AgentMessageRoleWrapper? role,
        ObjectExpression<RecordDataValue>.Builder? metadata)
    {
        AddConversationMessage.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("add_message"),
                DisplayName = this.FormatDisplayName(displayName),
                ConversationId = conversation,
                Message = PropertyPath.Create(variablePath),
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
