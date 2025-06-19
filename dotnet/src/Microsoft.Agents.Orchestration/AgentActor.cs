// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Runtime;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An actor that represents an <see cref="Agent"/>.
/// </summary>
public abstract class AgentActor : OrchestrationActor
{
    private AgentRunOptions? _options;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentActor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier of the agent.</param>
    /// <param name="runtime">The runtime associated with the agent.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agent">An <see cref="Agent"/>.</param>
    /// <param name="logger">The logger to use for the actor</param>
    protected AgentActor(AgentId id, IAgentRuntime runtime, OrchestrationContext context, Agent agent, ILogger? logger = null)
        : base(
            id,
            runtime,
            context,
            VerifyDescription(agent),
            logger)
    {
        this.Agent = agent;
    }

    /// <summary>
    /// Gets the associated agent.
    /// </summary>
    protected Agent Agent { get; }

    /// <summary>
    /// Gets or sets the current conversation thread used during agent communication.
    /// </summary>
    protected AgentThread? Thread { get; set; }

    /// <summary>
    /// Optionally overridden to create custom invocation options for the agent.
    /// </summary>
    protected virtual AgentRunOptions CreateInvokeOptions(Func<IReadOnlyCollection<ChatMessage>, Task> messageHandler) => new() { OnIntermediateMessages = messageHandler };

    /// <summary>
    /// Optionally overridden to introduce customer filtering logic for the response callback.
    /// </summary>
    /// <param name="response">The agent response</param>
    /// <returns>true if the response should be filtered (hidden)</returns>
    protected virtual bool ResponseCallbackFilter(ChatMessage response) => false;

    /// <summary>
    /// Invokes the agent with a single chat message.
    /// This method sets the message role to <see cref="ChatRole.User"/> and delegates to the overload accepting multiple messages.
    /// </summary>
    /// <param name="input">The chat message content to send.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A task that returns the response <see cref="ChatMessage"/>.</returns>
    protected ValueTask<ChatMessage> InvokeAsync(ChatMessage input, CancellationToken cancellationToken)
    {
        return this.InvokeAsync([input], cancellationToken);
    }

    /// <summary>
    /// Invokes the agent with input messages and respond with both streamed and regular messages.
    /// </summary>
    /// <param name="input">The list of chat messages to send.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A task that returns the response <see cref="ChatMessage"/>.</returns>
    protected async ValueTask<ChatMessage> InvokeAsync(IEnumerable<ChatMessage> input, CancellationToken cancellationToken)
    {
        this.Context.Cancellation.ThrowIfCancellationRequested();

        ChatMessage? response = null;

        AgentRunOptions options = this.GetOptions(HandleMessage);
        if (this.Context.StreamingResponseCallback == null)
        {
            // No need to utilize streaming if no callback is provided
            await this.InvokeAsync([.. input], options, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            await this.InvokeStreamingAsync([.. input], options, cancellationToken).ConfigureAwait(false);
        }

        return response ?? new ChatMessage(ChatRole.Assistant, string.Empty);

        async Task HandleMessage(IReadOnlyCollection<ChatMessage> messages)
        {
            // Keep track of most recent response for both invocation modes
            response = messages.LastOrDefault(); // %%% HACK - REVALUATE

            if (this.Context.ResponseCallback is not null)
            {
                await this.Context.ResponseCallback.Invoke(messages.Where(message => !this.ResponseCallbackFilter(message))).ConfigureAwait(false);
            }
        }
    }

    private async Task InvokeAsync(IReadOnlyCollection<ChatMessage> input, AgentRunOptions options, CancellationToken cancellationToken)
    {
        ChatResponse? lastResponse =
            await this.Agent.RunAsync(
                input,
                this.Thread,
                options,
                cancellationToken).ConfigureAwait(false);

        //this.Thread ??= lastResponse?.Thread; // %%% HACK
    }

    private async Task InvokeStreamingAsync(IReadOnlyCollection<ChatMessage> input, AgentRunOptions options, CancellationToken cancellationToken)
    {
        IAsyncEnumerable<ChatResponseUpdate> streamedResponses =
            this.Agent.RunStreamingAsync(
                input,
                this.Thread,
                options,
                cancellationToken);

        ChatResponseUpdate? lastStreamedResponse = null;
        await foreach (ChatResponseUpdate streamedResponse in streamedResponses.ConfigureAwait(false))
        {
            this.Context.Cancellation.ThrowIfCancellationRequested();

            //this.Thread ??= streamedResponse.Thread; // %%% HACK

            await HandleStreamedMessage(lastStreamedResponse, isFinal: false).ConfigureAwait(false);

            lastStreamedResponse = streamedResponse;
        }

        await HandleStreamedMessage(lastStreamedResponse, isFinal: true).ConfigureAwait(false);

        async ValueTask HandleStreamedMessage(ChatResponseUpdate? streamedResponse, bool isFinal)
        {
            if (this.Context.StreamingResponseCallback != null && streamedResponse != null)
            {
                await this.Context.StreamingResponseCallback.Invoke(streamedResponse, isFinal).ConfigureAwait(false);
            }
        }
    }

    private AgentRunOptions GetOptions(Func<IReadOnlyCollection<ChatMessage>, Task> messageHandler) => this._options ??= this.CreateInvokeOptions(messageHandler);

    private static string VerifyDescription(Agent agent)
    {
        return agent.Description ?? throw new ArgumentException($"Missing agent description: {agent.Name ?? agent.Id}", nameof(agent));
    }
}
