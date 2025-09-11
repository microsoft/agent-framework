// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Internal chat client that handle agent invocation details for the chat client pipeline.
/// </summary>
internal sealed class AgentInvokedChatClient : DelegatingChatClient
{
    private readonly AIAgent _agent;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvokedChatClient"/> class.
    /// </summary>
    /// <param name="agent">The agent handling the chat client.</param>
    /// <param name="chatClient">The chat client to invoke agents.</param>
    internal AgentInvokedChatClient(ChatClientAgent agent, IChatClient chatClient)
        : base(chatClient)
    {
        this._agent = Throw.IfNull(agent);
    }
}
