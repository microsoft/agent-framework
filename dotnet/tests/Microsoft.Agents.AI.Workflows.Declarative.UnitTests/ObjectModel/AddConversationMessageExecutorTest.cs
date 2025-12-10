// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
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

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        AgentMessageRoleWrapper role,
        string messageText)
    {
        // Arrange
        MockAgentProvider mockAgentProvider = new();
        AddConversationMessage model = this.CreateModel(
            this.FormatDisplayName(displayName),
            FormatVariablePath(variableName),
            "TestConversationId",
            role,
            messageText);

        AddConversationMessageExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        ChatMessage? testMessage = mockAgentProvider.TestMessages?.FirstOrDefault();
        Assert.NotNull(testMessage);
        VerifyModel(model, action);
        this.VerifyState(variableName, testMessage.ToRecord());
    }

    private AddConversationMessage CreateModel(
        string displayName,
        string messageVariable,
        string conversationId,
        AgentMessageRoleWrapper role,
        string messageText)
    {
        AddConversationMessage.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Message = PropertyPath.Create(messageVariable),
                ConversationId = StringExpression.Literal(conversationId),
                Role = role,
            };

        actionBuilder.Content.Add(new AddConversationMessageContent.Builder
        {
            Type = AgentMessageContentType.Text,
            Value = TemplateLine.Parse(messageText)
        });

        return AssignParent<AddConversationMessage>(actionBuilder);
    }
}
