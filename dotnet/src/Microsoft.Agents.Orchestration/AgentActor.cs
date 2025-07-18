// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An actor that represents an <see cref="Agent"/>.
/// </summary>
public abstract class AgentActor : OrchestrationActor
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentActor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier of the agent.</param>
    /// <param name="runtime">The runtime associated with the agent.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agent">An <see cref="Agent"/>.</param>
    /// <param name="logger">The logger to use for the actor</param>
    protected AgentActor(ActorId id, IAgentRuntime runtime, OrchestrationContext context, AIAgent agent, ILogger? logger = null)
        : base(id, runtime, context, agent.Description, logger)
    {
        this.Agent = agent;
        this.Thread = this.Agent.GetNewThread();
    }

    /// <summary>
    /// Gets the associated agent.
    /// </summary>
    protected AIAgent Agent { get; }

    /// <summary>
    /// Gets the current conversation thread used during agent communication.
    /// </summary>
    protected AgentThread Thread { get; private set; }

    /// <summary>
    /// Reset the conversation thread.
    /// </summary>
    protected void ResetThread()
    {
        this.Thread = this.Agent.GetNewThread();
    }

    /// <summary>
    /// Invokes the agent for a non-streamed responses.
    /// </summary>
    /// <param name="messages">The messages to send.</param>
    /// <param name="options">The options for running the agent.</param>
    /// <param name="cancellationToken">A cancellation token for the operation.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    /// <remarks>
    /// This method is not intended to be called directly; instead, use <see cref="RunAsync"/>.
    /// This method exists to be overridden in derived classes in order to customize the invocation of the agent by <see cref="RunAsync"/>.
    /// </remarks>
    protected virtual Task<AgentRunResponse> InvokeCoreAsync(
        IReadOnlyCollection<ChatMessage> messages, AgentRunOptions? options, CancellationToken cancellationToken) =>
        this.Agent.RunAsync([.. messages], this.Thread, options, cancellationToken);

    /// <summary>
    /// Invokes the agent for a streamed responses.
    /// </summary>
    /// <param name="messages">The messages to send.</param>
    /// <param name="options">The options for running the agent.</param>
    /// <param name="cancellationToken">A cancellation token for the operation.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    /// <remarks>
    /// This method is not intended to be called directly; instead, use <see cref="RunAsync"/>.
    /// This method exists to be overridden in derived classes in order to customize the invocation of the agent by <see cref="RunAsync"/>.
    /// </remarks>
    protected virtual IAsyncEnumerable<AgentRunResponseUpdate> InvokeStreamingCoreAsync(
        IReadOnlyCollection<ChatMessage> messages, AgentRunOptions? options, CancellationToken cancellationToken) =>
        this.Agent.RunStreamingAsync(messages, this.Thread, options, cancellationToken);

    /// <summary>
    /// Runs the agent with input messages and respond with both streamed and regular messages.
    /// </summary>
    /// <param name="input">The list of chat messages to send.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A task that returns the response <see cref="ChatMessage"/>.</returns>
    protected async ValueTask<ChatMessage> RunAsync(IEnumerable<ChatMessage> input, CancellationToken cancellationToken)
    {
        using CancellationTokenSource combined = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, this.Context.CancellationToken);
        cancellationToken = combined.Token;

        // Utilize streaming iff a streaming callback is provided; otherwise, use the non-streaming API.
        AgentRunResponse response;
        if (this.Context.StreamingResponseCallback is { } streamingCallback)
        {
            // For streaming, enumerate all the updates, invoking the callback for each, and storing them all.
            // Then convert them all into a single response instance.
            List<AgentRunResponseUpdate> updates = [];

            await foreach (AgentRunResponseUpdate update in this.InvokeStreamingCoreAsync([.. input], options: null, cancellationToken).WithCancellation(this.Context.CancellationToken).ConfigureAwait(false))
            {
                updates.Add(update);
                await streamingCallback(update).ConfigureAwait(false);
            }

            response = updates.ToAgentRunResponse();
        }
        else
        {
            // For non-streaming, just invoke the non-streaming method and get back the response.
            response = await this.InvokeCoreAsync([.. input], options: null, cancellationToken).ConfigureAwait(false);
        }

        // Regardless of whether we invoked streaming callbacks for individual updates, invoke the non-streaming callback with the final response instance.
        // This can be used as an indication of completeness if someone otherwise only cares about the streaming updates.
        if (this.Context.ResponseCallback is { } responseCallback)
        {
            await responseCallback.Invoke(response.Messages).ConfigureAwait(false);
        }

        return response.Messages.LastOrDefault() ?? new();
    }
}
