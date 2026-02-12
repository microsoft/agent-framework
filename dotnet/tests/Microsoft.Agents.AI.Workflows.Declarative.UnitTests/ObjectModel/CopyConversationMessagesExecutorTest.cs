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
/// Tests for <see cref="CopyConversationMessagesExecutor"/>.
/// </summary>
public sealed class CopyConversationMessagesExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task CopyMessagesWithSingleStringMessageAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CopyMessagesWithSingleStringMessageAsync),
            conversationId: "TestConversationId",
            messages: ValueExpression.Literal(StringDataValue.Create("Hello, how can I help you?")),
            expectedMessageCount: 1);
    }

    [Fact]
    public async Task CopyMessagesWithSingleRecordMessageAsync()
    {
        // Arrange
        ChatMessage testMessage = new(ChatRole.User, "Test message content");
        DataValue messageDataValue = testMessage.ToRecord().ToDataValue();
        Assert.IsType<RecordDataValue>(messageDataValue);
        RecordDataValue messageRecord = (RecordDataValue)messageDataValue;

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CopyMessagesWithSingleRecordMessageAsync),
            conversationId: "TestConversationId",
            messages: ValueExpression.Literal(messageRecord),
            expectedMessageCount: 1);
    }

    [Fact]
    public async Task CopyMessagesWithMultipleMessagesAsync()
    {
        // Arrange
        List<ChatMessage> testMessages =
        [
            new ChatMessage(ChatRole.User, "First message"),
            new ChatMessage(ChatRole.Assistant, "Second message"),
            new ChatMessage(ChatRole.User, "Third message")
        ];
        DataValue messagesDataValue = testMessages.ToTable().ToDataValue();
        Assert.IsType<TableDataValue>(messagesDataValue);
        TableDataValue messagesTable = (TableDataValue)messagesDataValue;

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CopyMessagesWithMultipleMessagesAsync),
            conversationId: "TestConversationId",
            messages: ValueExpression.Literal(messagesTable),
            expectedMessageCount: 3);
    }

    [Fact]
    public async Task CopyMessagesWithVariableExpressionAsync()
    {
        // Arrange
        List<ChatMessage> testMessages =
        [
            new ChatMessage(ChatRole.User, "Message from variable")
        ];
        TableValue messagesTable = testMessages.ToTable();
        this.State.Set("SourceMessages", messagesTable);

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CopyMessagesWithVariableExpressionAsync),
            conversationId: "TestConversationId",
            messages: ValueExpression.Variable(PropertyPath.TopicVariable("SourceMessages")),
            expectedMessageCount: 1);
    }

    [Fact]
    public async Task CopyMessagesToWorkflowConversationAsync()
    {
        // Arrange
        this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New("WorkflowConversationId"), VariableScopeNames.System);

        List<ChatMessage> testMessages =
        [
            new ChatMessage(ChatRole.User, "Message to workflow conversation")
        ];
        DataValue messagesDataValue = testMessages.ToTable().ToDataValue();
        Assert.IsType<TableDataValue>(messagesDataValue);
        TableDataValue messagesTable = (TableDataValue)messagesDataValue;

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CopyMessagesToWorkflowConversationAsync),
            conversationId: "WorkflowConversationId",
            messages: ValueExpression.Literal(messagesTable),
            expectedMessageCount: 1,
            expectWorkflowEvent: true);
    }

    [Fact]
    public async Task CopyMessagesToNonWorkflowConversationAsync()
    {
        // Arrange
        this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New("WorkflowConversationId"), VariableScopeNames.System);

        List<ChatMessage> testMessages =
        [
            new ChatMessage(ChatRole.User, "Message to non-workflow conversation")
        ];
        DataValue messagesDataValue = testMessages.ToTable().ToDataValue();
        Assert.IsType<TableDataValue>(messagesDataValue);
        TableDataValue messagesTable = (TableDataValue)messagesDataValue;

        // Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CopyMessagesToNonWorkflowConversationAsync),
            conversationId: "DifferentConversationId",
            messages: ValueExpression.Literal(messagesTable),
            expectedMessageCount: 1,
            expectWorkflowEvent: false);
    }

    [Fact]
    public async Task CopyMessagesWithBlankDataValueAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CopyMessagesWithBlankDataValueAsync),
            conversationId: "TestConversationId",
            messages: ValueExpression.Literal(DataValue.Blank()),
            expectedMessageCount: 0);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string conversationId,
        ValueExpression messages,
        int expectedMessageCount,
        bool expectWorkflowEvent = false)
    {
        // Arrange
        MockAgentProvider mockAgentProvider = new();
        mockAgentProvider.TestMessages.Clear();

        CopyConversationMessages model = this.CreateModel(
            this.FormatDisplayName(displayName),
            conversationId,
            messages);

        CopyConversationMessagesExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action);

        // Assert
        Assert.Equal(expectedMessageCount, mockAgentProvider.TestMessages.Count);
        VerifyModel(model, action);

        AgentResponseEvent[] responseEvents = events.OfType<AgentResponseEvent>().ToArray();
        if (expectWorkflowEvent && expectedMessageCount > 0)
        {
            Assert.NotEmpty(responseEvents);
            AgentResponseEvent responseEvent = responseEvents.First();
            Assert.Equal(action.Id, responseEvent.ExecutorId);
            Assert.NotNull(responseEvent.Response);
            Assert.Equal(expectedMessageCount, responseEvent.Response.Messages.Count);
        }
        else
        {
            Assert.Empty(responseEvents);
        }
    }

    private CopyConversationMessages CreateModel(
        string displayName,
        string conversationId,
        ValueExpression messages)
    {
        CopyConversationMessages.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            ConversationId = StringExpression.Literal(conversationId),
            Messages = messages
        };

        return AssignParent<CopyConversationMessages>(actionBuilder);
    }
}
