// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Moq;

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

    [Fact]
    public async Task RetrieveMessageWithSensitiveMessageIdThrowsAsync()
    {
        // Arrange
        this.State.Set("MessageId", FormulaValue.New("sensitive-message"), sensitivity: SensitivityLevel.Sensitive);
        MockAgentProvider mockAgentProvider = new();
        RetrieveConversationMessage.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(nameof(RetrieveMessageWithSensitiveMessageIdThrowsAsync)),
            Message = PropertyPath.Create(FormatVariablePath("TestMessage")),
            ConversationId = StringExpression.Literal("DefaultConversationId"),
            MessageId = StringExpression.Variable(PropertyPath.TopicVariable("MessageId")),
        };
        RetrieveConversationMessage model = AssignParent<RetrieveConversationMessage>(builder);
        RetrieveConversationMessageExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        Task ExecuteAsync() => this.ExecuteAsync(action);

        // Assert
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(ExecuteAsync);
        Assert.Contains("message ID", exception.Message);
        mockAgentProvider.Verify(
            provider => provider.GetMessageAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RetrieveMessageWithSensitiveConversationIdThrowsAsync()
    {
        // Arrange
        this.State.Set("ConversationId", FormulaValue.New("sensitive-conversation"), sensitivity: SensitivityLevel.Sensitive);
        MockAgentProvider mockAgentProvider = new();
        RetrieveConversationMessage.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(nameof(RetrieveMessageWithSensitiveConversationIdThrowsAsync)),
            Message = PropertyPath.Create(FormatVariablePath("TestMessage")),
            ConversationId = StringExpression.Variable(PropertyPath.TopicVariable("ConversationId")),
            MessageId = StringExpression.Literal("DefaultMessageId"),
        };
        RetrieveConversationMessage model = AssignParent<RetrieveConversationMessage>(builder);
        RetrieveConversationMessageExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        Task ExecuteAsync() => this.ExecuteAsync(action);

        // Assert
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(ExecuteAsync);
        Assert.Contains("conversation ID", exception.Message);
        mockAgentProvider.Verify(
            provider => provider.GetMessageAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName)
    {
        // Arrange
        MockAgentProvider mockAgentProvider = new();

        RetrieveConversationMessage model = this.CreateModel(
            this.FormatDisplayName(displayName),
            FormatVariablePath(variableName),
            "TestConversationId",
            "DefaultMessageId");

        RetrieveConversationMessageExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        ChatMessage? testMessage = mockAgentProvider.TestMessages?.FirstOrDefault();
        Assert.NotNull(testMessage);
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
                DisplayName = this.FormatDisplayName(displayName),
                Message = PropertyPath.Create(messageVariable),
                ConversationId = StringExpression.Literal(conversationId),
                MessageId = StringExpression.Literal(messageId)
            };

        return AssignParent<RetrieveConversationMessage>(actionBuilder);
    }
}
