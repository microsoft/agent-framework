// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Agents.AI.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.A2A.Internal;

/// <summary>
/// A2A agent that wraps an existing AIAgent and provides A2A-specific thread wrapping.
/// </summary>
internal sealed class A2AAgentWrapper
{
    private readonly AgentProxy _agentProxy;

    public A2AAgentWrapper(
        IActorClient actorClient,
        AIAgent innerAgent,
        ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNullOrEmpty(innerAgent.Name);

        this._agentProxy = new AgentProxy(innerAgent.Name, actorClient);
    }

    public async Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
    {
        var contextId = messageSendParams.Message.ContextId ?? Guid.NewGuid().ToString("N");
        var chatMessages = messageSendParams.ToChatMessages();

        var thread = this._agentProxy.GetNewThread(contextId);
        var response = await this._agentProxy.RunAsync(messages: chatMessages, thread: thread, options: null, cancellationToken: cancellationToken).ConfigureAwait(false);

        return response.ToMessage(contextId);
    }
}
