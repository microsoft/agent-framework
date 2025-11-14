// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="RetrieveConversationMessageExecutor"/>.
/// </summary>
public sealed class RetrieveConversationMessageExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task RetrieveMessageSuccessfullyAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(nameof(RetrieveMessageSuccessfullyAsync),
            "TestMessage");
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName)
    {
        // Arrange
        MockAgentProvider mockAgentProvider = new();
        ChatMessage testMessage = mockAgentProvider.TestChatMessage ?? new ChatMessage();

        RetrieveConversationMessage model = this.CreateModel(
            this.FormatDisplayName(displayName),
            FormatVariablePath(variableName),
            "TestConversationId",
            testMessage.MessageId ?? "DefaultMessageId");

        RetrieveConversationMessageExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState(variableName, testMessage.ToRecord());
    }

    private RetrieveConversationMessage CreateModel(
        string displayName,
        string messageVariable,
        string conversationId,
        string messageId)
    {
        RetrieveConversationMessage.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = displayName,
                Message = PropertyPath.Create(messageVariable),
                ConversationId = StringExpression.Literal(conversationId),
                MessageId = StringExpression.Literal(messageId)
            };

        return AssignParent<RetrieveConversationMessage>(actionBuilder);
    }
}
