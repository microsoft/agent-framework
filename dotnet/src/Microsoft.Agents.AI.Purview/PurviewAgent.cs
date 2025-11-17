// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// A middleware agent that connects to Microsoft Purview.
/// </summary>
internal class PurviewAgent : AIAgent, IDisposable
{
    private readonly AIAgent _innerAgent;
    private readonly PurviewWrapper _purviewWrapper;

    /// <summary>
    /// Initializes a new instance of the <see cref="PurviewAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The agent-framework agent that the middleware wraps.</param>
    /// <param name="purviewWrapper">The purview wrapper used to interact with the Purview service.</param>
    public PurviewAgent(AIAgent innerAgent, PurviewWrapper purviewWrapper)
    {
        this._innerAgent = innerAgent;
        this._purviewWrapper = purviewWrapper;
    }

    /// <inheritdoc/>
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return this._innerAgent.DeserializeThread(serializedThread, jsonSerializerOptions);
    }

    /// <inheritdoc/>
    public override AgentThread GetNewThread()
    {
        return this._innerAgent.GetNewThread();
    }

    /// <inheritdoc/>
    public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this._purviewWrapper.ProcessAgentContentAsync(messages, thread, options, this._innerAgent, cancellationToken);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var response = await this._purviewWrapper.ProcessAgentContentAsync(messages, thread, options, this._innerAgent, cancellationToken).ConfigureAwait(false);
        foreach (var update in response.ToAgentRunResponseUpdates())
        {
            yield return update;
        }
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        if (this._innerAgent is IDisposable disposableAgent)
        {
            disposableAgent.Dispose();
        }

        this._purviewWrapper.Dispose();
    }
}
