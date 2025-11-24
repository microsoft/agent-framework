// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="RetrieveConversationMessagesExecutor"/>.
/// </summary>
public sealed class RetrieveConversationMessagesExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task RetrieveAllMessagesSuccessfullyAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            nameof(RetrieveAllMessagesSuccessfullyAsync),
            "TestMessages",
            "TestConversationId");
    }

    [Fact]
    public async Task RetrieveMessagesWithOptionalValuesAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            nameof(RetrieveMessagesWithOptionalValuesAsync),
            "TestMessages",
            "TestConversationId",
            limit: IntExpression.Literal(2),
            after: StringExpression.Literal("11/01/2025"),
            before: StringExpression.Literal("12/01/2025"),
            sortOrder: EnumExpression<AgentMessageSortOrderWrapper>.Literal(AgentMessageSortOrderWrapper.Get(AgentMessageSortOrder.NewestFirst)));
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        string conversationId,
        IntExpression? limit = null,
        StringExpression? after = null,
        StringExpression? before = null,
        EnumExpression<AgentMessageSortOrderWrapper>? sortOrder = null)
    {
        // Arrange
        MockAgentProvider mockAgentProvider = new();

        RetrieveConversationMessages model = this.CreateModel(
            this.FormatDisplayName(displayName),
            FormatVariablePath(variableName),
            conversationId,
            limit,
            after,
            before,
            sortOrder);

        RetrieveConversationMessagesExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        var testMessages = mockAgentProvider.TestMessages;
        Assert.NotNull(testMessages);
        VerifyModel(model, action);
        this.VerifyState(variableName, testMessages.ToTable());
    }

    private RetrieveConversationMessages CreateModel(
        string displayName,
        string variableName,
        string conversationId,
        IntExpression? limit,
        StringExpression? after,
        StringExpression? before,
        EnumExpression<AgentMessageSortOrderWrapper>? sortOrder)
    {
        RetrieveConversationMessages.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Messages = PropertyPath.Create(variableName),
                ConversationId = StringExpression.Literal(conversationId)
            };

        if (limit is not null)
        {
            actionBuilder.Limit = limit;
        }

        if (after is not null)
        {
            actionBuilder.MessageAfter = after;
        }

        if (before is not null)
        {
            actionBuilder.MessageBefore = before;
        }

        if (sortOrder is not null)
        {
            actionBuilder.SortOrder = sortOrder;
        }

        return AssignParent<RetrieveConversationMessages>(actionBuilder);
    }
}
