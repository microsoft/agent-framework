// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using Microsoft.Shared.Diagnostics;

#pragma warning disable CS0419 // Ambiguous reference in cref attribute

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides context information for agent invocation callback middleware.
/// </summary>
public sealed class AgentRunContext : CallbackContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunContext"/> class.
    /// </summary>
    /// <param name="agent">The agent instance being invoked.</param>
    /// <param name="messages">The messages being passed to the agent.</param>
    /// <param name="thread">The conversation thread for the invocation.</param>
    /// <param name="options">The options for the agent invocation.</param>
    /// <param name="isStreaming">A value indicating whether this is a streaming invocation.</param>
    /// <param name="cancellationToken">The cancellation token for the operation.</param>
    public AgentRunContext(
        AIAgent agent,
        IEnumerable<ChatMessage> messages,
        AgentThread? thread,
        AgentRunOptions? options,
        bool isStreaming,
        CancellationToken cancellationToken)
        : base(agent, cancellationToken)
    {
        this.Messages = Throw.IfNull(messages).ToList();
        this.Thread = thread;
        this.Options = options;
        this.IsStreaming = isStreaming;
    }

    /// <summary>
    /// Gets the messages being passed to the agent.
    /// </summary>
    public IList<ChatMessage> Messages { get; set; }

    /// <summary>
    /// Gets the conversation thread for the invocation.
    /// </summary>
    public AgentThread? Thread { get; }

    /// <summary>
    /// Gets the options for the agent invocation.
    /// </summary>
    public AgentRunOptions? Options { get; set; }

    /// <summary>
    /// Gets a value indicating whether this is a streaming invocation.
    /// </summary>
    public bool IsStreaming { get; }

    /// <summary>
    /// Set the streaming response of the agent invocation.
    /// </summary>
    /// <param name="streamingResponse">The streaming response to set.</param>
    /// <exception cref="System.InvalidOperationException">Can't set a streaming response for a non-streaming invocation.</exception>
    public void SetRunStreamingResponse(IAsyncEnumerable<AgentRunResponseUpdate>? streamingResponse)
    {
        if (this.IsStreaming is false)
        {
            throw new System.InvalidOperationException("Cannot set a streaming response for a non-streaming invocation.");
        }

        this.RawResponse = streamingResponse;
    }

    /// <summary>
    /// Set the non-streaming response of the agent invocation.
    /// </summary>
    /// <param name="response">The <see cref="AgentRunResponse"/> to set.</param>
    /// <exception cref="System.InvalidOperationException">Can't set a non-streaming response for a streaming invocation.</exception>
    public void SetRunResponse(AgentRunResponse? response)
    {
        if (this.IsStreaming is true)
        {
            throw new System.InvalidOperationException("Cannot set a non-streaming response for a streaming invocation.");
        }
        this.RawResponse = response;
    }

    /// <summary>
    /// Gets or sets the raw response of the agent invocation.
    /// </summary>
    /// <remarks>
    /// When <see cref="IsStreaming"/> is <see langword="false" /> for non-streaming this property will be a <see cref="AgentRunResponse"/>
    /// When <see cref="IsStreaming"/> is <see langword="true" /> this property will return a <see cref="IAsyncEnumerable{AgentRunResponseUpdate}"/>
    /// where T is a <see cref="AgentRunResponseUpdate"/>.
    /// </remarks>
    public object? RawResponse { get; private set; }

    /// <summary>
    /// Gets the result of the agent's run as an <see cref="AgentRunResponse"/> object.
    /// </summary>
    /// <remarks>
    /// This property will be non-null only if the invocation was already performed in non-streaming mode.
    /// </remarks>
    public AgentRunResponse? RunResponse => this.RawResponse as AgentRunResponse;

    /// <summary>
    /// Gets the result of the agent's run as an asynchronous stream of <see cref="AgentRunResponseUpdate"/> objects.
    /// </summary>
    /// <remarks>
    /// This property will be non-null only if the invocation was already performed in streaming mode.
    /// </remarks>
    public IAsyncEnumerable<AgentRunResponseUpdate>? RunStreamingResponse => this.RawResponse as IAsyncEnumerable<AgentRunResponseUpdate>;
}
