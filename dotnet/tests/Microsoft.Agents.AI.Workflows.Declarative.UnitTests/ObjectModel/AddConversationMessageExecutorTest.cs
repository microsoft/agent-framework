// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="AddConversationMessageExecutor"/>.
/// </summary>
public sealed class AddConversationMessageExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Theory]
    [InlineData(AgentMessageRole.User)]
    [InlineData(AgentMessageRole.Agent)]
    public async Task AddMessageSuccessfullyAsync(AgentMessageRole role)
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(AddMessageSuccessfullyAsync),
            variableName: "TestMessage",
            role: AgentMessageRoleWrapper.Get(role),
            messageText: $"Hello from {role}");
    }

    [Theory]
    [InlineData(AgentMessageRole.User)]
    [InlineData(AgentMessageRole.Agent)]
    public async Task AddMessageToWorkflowAsync(AgentMessageRole role)
    {
        // Arrange
        this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New("WorkflowConversationId"), VariableScopeNames.System);

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(AddMessageToWorkflowAsync),
            variableName: "TestMessage",
            role: AgentMessageRoleWrapper.Get(role),
            conversationId: "WorkflowConversationId",
            messageText: $"Hello from {role}");
    }

    [Theory]
    [InlineData(AgentMessageRole.User)]
    [InlineData(AgentMessageRole.Agent)]
    public async Task AddMessageWithMetadataAsync(AgentMessageRole role)
    {
        // Arrange
        Dictionary<string, string> metadataValues =
            new()
            {
                ["Key1"] = "Value1",
                ["Key2"] = "Value2",
            };
        RecordDataValue metadataRecord = metadataValues.ToRecordValue();

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(AddMessageWithMetadataAsync),
            variableName: "TestMessage",
            role: AgentMessageRoleWrapper.Get(role),
            messageText: $"Hello from {role}",
            metadata: metadataRecord);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        AgentMessageRoleWrapper role,
        string messageText,
        string? conversationId = null,
        RecordDataValue? metadata = null)
    {
        // Arrange
        MockAgentProvider mockAgentProvider = new();
        AddConversationMessage model =
            this.CreateModel(
                this.FormatDisplayName(displayName),
                FormatVariablePath(variableName),
                conversationId ?? "TestConversationId",
                role,
                messageText,
                metadata);

        AddConversationMessageExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        ChatMessage? testMessage = mockAgentProvider.TestMessages?.LastOrDefault();
        Assert.NotNull(testMessage);
        VerifyModel(model, action);
        this.VerifyState(variableName, testMessage.ToRecord());
        if (metadata is not null)
        {
            Assert.NotNull(testMessage.AdditionalProperties);
            Assert.NotEmpty(testMessage.AdditionalProperties);
        }
    }

    private AddConversationMessage CreateModel(
        string displayName,
        string messageVariable,
        string conversationId,
        AgentMessageRoleWrapper role,
        string messageText,
        RecordDataValue? metadata)
    {
        ObjectExpression<RecordDataValue>.Builder? metadataExpression = null;
        if (metadata is not null)
        {
            metadataExpression = ObjectExpression<RecordDataValue>.Literal(metadata).ToBuilder();
        }

        AddConversationMessage.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Message = PropertyPath.Create(messageVariable),
                ConversationId = StringExpression.Literal(conversationId),
                Role = role,
                Metadata = metadataExpression,
            };

        actionBuilder.Content.Add(new AddConversationMessageContent.Builder
        {
            Type = AgentMessageContentType.Text,
            Value = TemplateLine.Parse(messageText)
        });

        return AssignParent<AddConversationMessage>(actionBuilder);
    }
}
