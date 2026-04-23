// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Valkey.UnitTests;

internal sealed class TestAgentSession : AgentSession
{
    public TestAgentSession()
    {
        this.StateBag = new AgentSessionStateBag();
    }
}

internal static class TestHelpers
{
    internal static readonly AIAgent MockAgent = new Mock<AIAgent>().Object;

    internal static ChatHistoryProvider.InvokingContext CreateChatHistoryInvokingContext(
        IEnumerable<ChatMessage>? requestMessages = null)
    {
#pragma warning disable MAAI001
        return new ChatHistoryProvider.InvokingContext(
            MockAgent,
            new TestAgentSession(),
            requestMessages ?? [new ChatMessage(ChatRole.User, "test")]);
#pragma warning restore MAAI001
    }

    internal static ChatHistoryProvider.InvokedContext CreateChatHistoryInvokedContext(
        IEnumerable<ChatMessage> requestMessages,
        IEnumerable<ChatMessage> responseMessages)
    {
#pragma warning disable MAAI001
        return new ChatHistoryProvider.InvokedContext(
            MockAgent,
            new TestAgentSession(),
            requestMessages,
            responseMessages);
#pragma warning restore MAAI001
    }

    internal static AIContextProvider.InvokedContext CreateContextProviderInvokedContext(
        IEnumerable<ChatMessage> requestMessages,
        IEnumerable<ChatMessage> responseMessages)
    {
#pragma warning disable MAAI001
        return new AIContextProvider.InvokedContext(
            MockAgent,
            new TestAgentSession(),
            requestMessages,
            responseMessages);
#pragma warning restore MAAI001
    }
}
