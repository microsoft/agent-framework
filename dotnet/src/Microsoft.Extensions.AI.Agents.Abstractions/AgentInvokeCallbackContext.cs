// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using Microsoft.Shared.Diagnostics;

#pragma warning disable CS0419 // Ambiguous reference in cref attribute

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides context information for agent invocation callback middleware.
/// </summary>
public class AgentInvokeCallbackContext : CallbackContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvokeCallbackContext"/> class.
    /// </summary>
    /// <param name="agent">The agent instance being invoked.</param>
    /// <param name="messages">The messages being passed to the agent.</param>
    /// <param name="thread">The conversation thread for the invocation.</param>
    /// <param name="options">The options for the agent invocation.</param>
    /// <param name="isStreaming">A value indicating whether this is a streaming invocation.</param>
    /// <param name="cancellationToken">The cancellation token for the operation.</param>
    internal AgentInvokeCallbackContext(
        AIAgent agent,
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread,
        AgentRunOptions? options,
        bool isStreaming,
        CancellationToken cancellationToken)
        : base(agent, cancellationToken)
    {
        this.Messages = Throw.IfNull(messages);
        this.Thread = thread;
        this.Options = options;
        this.IsStreaming = isStreaming;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvokeCallbackContext"/> class by copying the values from
    /// another instance.
    /// </summary>
    /// <remarks>
    /// This constructor sets the specializations to work as decorators of this instance.
    /// </remarks>
    /// <param name="other">The instance of <see cref="AgentInvokeCallbackContext"/> to copy values from. Cannot be <see langword="null"/>.</param>
    protected AgentInvokeCallbackContext(AgentInvokeCallbackContext other)
        : base(other)
    {
        this.Messages = other.Messages;
        this.Thread = other.Thread;
        this.Options = other.Options;
        this.IsStreaming = other.IsStreaming;
        this.Result = other.Result;
    }

    /// <summary>
    /// Gets the messages being passed to the agent.
    /// </summary>
    public IReadOnlyCollection<ChatMessage> Messages { get; }

    /// <summary>
    /// Gets the conversation thread for the invocation.
    /// </summary>
    public AgentThread? Thread { get; }

    /// <summary>
    /// Gets the options for the agent invocation.
    /// </summary>
    public AgentRunOptions? Options { get; }

    /// <summary>
    /// Gets a value indicating whether this is a streaming invocation.
    /// </summary>
    public bool IsStreaming { get; }

    /// <summary>
    /// Gets or sets the result of the agent invocation.
    /// </summary>
    /// <remarks>
    /// When <see cref="IsStreaming"/> is <see langword="false" /> for non-streaming this property will be a <see cref="ChatResponse"/>
    /// When <see cref="IsStreaming"/> is <see langword="true" /> this property will return a <see cref="IAsyncEnumerable{AgentRunResponseUpdate}"/>
    /// where T is a <see cref="AgentRunResponseUpdate"/>.
    /// </remarks>
    public object? Result { get; set; }

    /// <summary>
    /// Gets the result of the agent's run as an <see cref="AgentRunResponse"/> object.
    /// </summary>
    /// <remarks>
    /// This property will be non-null only if the invocation was already performed in non-streaming mode.
    /// </remarks>
    public AgentRunResponse? RunResult => this.Result as AgentRunResponse;

    /// <summary>
    /// Gets the result of the agent's run as an asynchronous stream of <see cref="AgentRunResponseUpdate"/> objects.
    /// </summary>
    /// <remarks>
    /// This property will be non-null only if the invocation was already performed in streaming mode.
    /// </remarks>
    public IAsyncEnumerable<AgentRunResponseUpdate>? RunStreamResult => this.Result as IAsyncEnumerable<AgentRunResponseUpdate>;
}
