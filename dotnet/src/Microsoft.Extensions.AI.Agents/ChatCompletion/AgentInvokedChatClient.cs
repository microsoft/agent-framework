// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Internal chat client that handle agent invocation details for the chat client pipeline.
/// </summary>
internal sealed class AgentInvokedChatClient : DelegatingChatClient
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvokedChatClient"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to invoke agents.</param>
    internal AgentInvokedChatClient(IChatClient chatClient)
        : base(chatClient)
    {
    }
}
