// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.ChatCompletion;

/// <summary>
/// Internal chat client that handle agent invocation details for the chat client pipeline.
/// </summary>
internal sealed class AgentInvokingChatClient : DelegatingChatClient
{
    internal AgentInvokingChatClient(IChatClient chatClient, ILoggerFactory loggerFactory, IServiceProvider services)
        : base(chatClient)
    {
    }
}
