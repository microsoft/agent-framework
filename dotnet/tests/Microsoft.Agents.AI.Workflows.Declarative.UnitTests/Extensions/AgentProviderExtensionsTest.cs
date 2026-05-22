// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

/// <summary>
/// Tests for <see cref="AgentProviderExtensions.InvokeAgentAsync"/>.
/// </summary>
public sealed class AgentProviderExtensionsTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    private const string WorkflowConversationId = "workflow-conv-id";
    private const string AgentName = "test-agent";

    [Fact]
    public Task AutoSendFalseOnWorkflowConversationSuppressesResponseEventsAsync() =>
        this.RunAsync(autoSend: false, conversationId: WorkflowConversationId, expectResponseEvents: false);

    [Fact]
    public Task AutoSendTrueOnWorkflowConversationEmitsResponseEventsAsync() =>
        this.RunAsync(autoSend: true, conversationId: WorkflowConversationId, expectResponseEvents: true);

    [Fact]
    public Task AutoSendFalseOnExternalConversationSuppressesResponseEventsAsync() =>
        this.RunAsync(autoSend: false, conversationId: "other-conv-id", expectResponseEvents: false);

    [Fact]
    public Task AutoSendTrueOnExternalConversationEmitsResponseEventsAndCopiesMessagesAsync() =>
        this.RunAsync(
            autoSend: true,
            conversationId: "other-conv-id",
            expectResponseEvents: true,
            expectCrossConversationCopy: true);

    private async Task RunAsync(
        bool autoSend,
        string conversationId,
        bool expectResponseEvents,
        bool expectCrossConversationCopy = false)
    {
        // Arrange: seed the workflow conversation id so IsWorkflowConversation can recognize it.
        this.State.Set(
            SystemScope.Names.ConversationId,
            FormulaValue.New(WorkflowConversationId),
            VariableScopeNames.System);

        MockAgentProvider mockProvider = new();
        AgentResponseUpdate[] updates =
        [
            new(ChatRole.Assistant, "hello "),
            new(ChatRole.Assistant, "world"),
        ];
        mockProvider
            .Setup(p => p.InvokeAgentAsync(
                AgentName,
                It.IsAny<string?>(),
                It.IsAny<string?>(),
                It.IsAny<IEnumerable<ChatMessage>?>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(updates));

        List<(string ConversationId, ChatMessage Message)> copiedMessages = [];
        mockProvider
            .Setup(p => p.CreateMessageAsync(
                It.IsAny<string>(),
                It.IsAny<ChatMessage>(),
                It.IsAny<CancellationToken>()))
            .Returns<string, ChatMessage, CancellationToken>(
                (convId, msg, _) =>
                {
                    copiedMessages.Add((convId, msg));
                    return Task.FromResult(msg);
                });

        string actionId = this.CreateActionId().Value;

        // Act
        WorkflowEvent[] events =
            await this.ExecuteAsync(
                actionId,
                async (IWorkflowContext context, ActionExecutorResult _, CancellationToken cancellationToken) =>
                {
                    await mockProvider.Object.InvokeAgentAsync(
                        actionId,
                        context,
                        AgentName,
                        conversationId,
                        autoSend,
                        cancellationToken: cancellationToken).ConfigureAwait(false);
                });

        // Assert
        int updateEventCount = events.OfType<AgentResponseUpdateEvent>().Count();
        int responseEventCount = events.OfType<AgentResponseEvent>().Count();

        if (expectResponseEvents)
        {
            Assert.Equal(updates.Length, updateEventCount);
            Assert.Equal(1, responseEventCount);
        }
        else
        {
            Assert.Equal(0, updateEventCount);
            Assert.Equal(0, responseEventCount);
        }

        if (expectCrossConversationCopy)
        {
            Assert.NotEmpty(copiedMessages);
            Assert.All(copiedMessages, c => Assert.Equal(WorkflowConversationId, c.ConversationId));
        }
        else
        {
            Assert.Empty(copiedMessages);
        }
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(IEnumerable<AgentResponseUpdate> updates)
    {
        foreach (AgentResponseUpdate update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }
}
