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
    protected AgentActor(ActorId id, IAgentRuntime runtime, OrchestrationContext context, Agent agent, ILogger? logger = null)
        : base(
            id,
            runtime,
            context,
            agent.Description,
            logger)
    {
        this.Agent = agent;
        this.Thread = this.Agent.GetNewThread();
    }

    /// <summary>
    /// Gets the associated agent.
    /// </summary>
    protected Agent Agent { get; }

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
    /// Invokes the agent for a regular (not streamed) response.
    /// </summary>
    /// <param name="messages">The messages to send.</param>
    /// <param name="options">The options for running the agent.</param>
    /// <param name="cancellationToken">A cancellation token for the operation.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    /// <remarks>
    /// Override this method to customize the invocation of the agent.
    /// </remarks>
    protected virtual Task InvokeAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentRunOptions options,
        CancellationToken cancellationToken = default) =>
        this.Agent.RunAsync(
            [.. messages],
            this.Thread,
            options,
            cancellationToken);

    /// <summary>
    /// Invokes the agent for a streamed response.
    /// </summary>
    /// <param name="messages">The messages to send.</param>
    /// <param name="options">The options for running the agent.</param>
    /// <param name="cancellationToken">A cancellation token for the operation.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    /// <remarks>
    /// Override this method to customize the invocation of the agent.
    /// </remarks>
    protected virtual IAsyncEnumerable<ChatResponseUpdate> InvokeStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentRunOptions options, CancellationToken cancellationToken) =>
        this.Agent.RunStreamingAsync(
            messages,
            this.Thread,
            options,
            cancellationToken);

    /// <summary>
    /// Invokes the agent with a single chat message.
    /// This method sets the message role to <see cref="ChatRole.User"/> and delegates to the overload accepting multiple messages.
    /// </summary>
    /// <param name="input">The chat message content to send.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A task that returns the response <see cref="ChatMessage"/>.</returns>
    protected ValueTask<ChatMessage> InvokeAsync(ChatMessage input, CancellationToken cancellationToken) =>
        this.InvokeAsync([input], cancellationToken);

    /// <summary>
    /// Invokes the agent with input messages and respond with both streamed and regular messages.
    /// </summary>
    /// <param name="input">The list of chat messages to send.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A task that returns the response <see cref="ChatMessage"/>.</returns>
    protected async ValueTask<ChatMessage> InvokeAsync(IEnumerable<ChatMessage> input, CancellationToken cancellationToken)
    {
        this.Context.Cancellation.ThrowIfCancellationRequested();

        List<ChatMessage>? responseMessages = [];
        ChatResponse response = new(responseMessages);

        AgentRunOptions options =
            new()
            {
                OnIntermediateMessages = HandleMessage,
            };

        if (this.Context.StreamingResponseCallback == null)
        {
            // No need to utilize streaming if no callback is provided
            await this.InvokeAsync([.. input], options, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            IAsyncEnumerable<ChatResponseUpdate> streamedResponses = this.InvokeStreamingAsync([.. input], options, cancellationToken);
            ChatResponseUpdate? lastStreamedResponse = null;
            await foreach (ChatResponseUpdate streamedResponse in streamedResponses.ConfigureAwait(false))
            {
                this.Context.Cancellation.ThrowIfCancellationRequested();

                await HandleStreamedMessage(lastStreamedResponse, isFinal: false).ConfigureAwait(false);

                lastStreamedResponse = streamedResponse;
            }

            await HandleStreamedMessage(lastStreamedResponse, isFinal: true).ConfigureAwait(false);
        }

        return response.Messages.Last();

        async Task HandleMessage(IReadOnlyCollection<ChatMessage> messages)
        {
            responseMessages?.AddRange(messages);

            if (this.Context.ResponseCallback is not null)
            {
                await this.Context.ResponseCallback.Invoke(messages).ConfigureAwait(false);
            }
        }

        async ValueTask HandleStreamedMessage(ChatResponseUpdate? streamedResponse, bool isFinal)
        {
            if (this.Context.StreamingResponseCallback != null && streamedResponse != null)
            {
                await this.Context.StreamingResponseCallback.Invoke(streamedResponse, isFinal).ConfigureAwait(false);
            }
        }
    }
}
