// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Internal chat client that handle agent invocation details for the chat client pipeline.
/// </summary>
internal sealed class AgentInvokingChatClient : DelegatingChatClient
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvokingChatClient"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to invoke agents.</param>
    internal AgentInvokingChatClient(IChatClient chatClient)
        : base(chatClient)
    {
    }
}
