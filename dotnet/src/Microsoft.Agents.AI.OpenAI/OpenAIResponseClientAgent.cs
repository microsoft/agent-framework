// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace OpenAI;

/// <summary>
/// Provides an <see cref="AIAgent"/> backed by an OpenAI Responses implementation.
/// </summary>
public class OpenAIResponseClientAgent : DelegatingAIAgent
{
    /// <summary>
    /// Initialize an instance of <see cref="OpenAIResponseClientAgent"/>.
    /// </summary>
    /// <param name="client">Instance of <see cref="OpenAIResponseClient"/></param>
    /// <param name="instructions">Optional instructions for the agent.</param>
    /// <param name="name">Optional name for the agent.</param>
    /// <param name="description">Optional description for the agent.</param>
    /// <param name="loggerFactory">Optional instance of <see cref="ILoggerFactory"/></param>
    public OpenAIResponseClientAgent(
        OpenAIResponseClient client,
        string? instructions = null,
        string? name = null,
        string? description = null,
        ILoggerFactory? loggerFactory = null) :
        this(client, new()
        {
            Name = name,
            Description = description,
            ChatOptions = new ChatOptions() { Instructions = instructions },
        }, loggerFactory)
    {
    }

    /// <summary>
    /// Initialize an instance of <see cref="OpenAIResponseClientAgent"/>.
    /// </summary>
    /// <param name="client">Instance of <see cref="OpenAIResponseClient"/></param>
    /// <param name="options">Options to create the agent.</param>
    /// <param name="loggerFactory">Optional instance of <see cref="ILoggerFactory"/></param>
    public OpenAIResponseClientAgent(
        OpenAIResponseClient client, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null) :
        base(new ChatClientAgent(Throw.IfNull(client).AsIChatClient(), options, loggerFactory))
    {
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent response.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="OpenAIResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public virtual async Task<OpenAIResponse> RunAsync(
        IEnumerable<ResponseItem> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var response = await this.RunAsync(messages.AsChatMessages(), thread, options, cancellationToken).ConfigureAwait(false);

        return response.AsOpenAIResponse();
    }

    /// <summary>
    /// Run the agent streaming with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent response.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="OpenAIResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public virtual async IAsyncEnumerable<StreamingResponseUpdate> RunStreamingAsync(
        IEnumerable<ResponseItem> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var response = this.RunStreamingAsync(messages.AsChatMessages(), thread, options, cancellationToken);

        await foreach (var update in response.ConfigureAwait(false))
        {
            switch (update.RawRepresentation)
            {
                case StreamingResponseUpdate rawUpdate:
                    yield return rawUpdate;
                    break;

                case ChatResponseUpdate { RawRepresentation: StreamingResponseUpdate rawUpdate }:
                    yield return rawUpdate;
                    break;

                default:
                    // TODO: The OpenAI library does not currently expose model factory methods for creating
                    // StreamingResponseUpdates. We are thus unable to manufacture such instances when there isn't
                    // already one in the update and instead skip them.
                    break;
            }
        }
    }

    /// <inheritdoc/>
    public sealed override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
        base.RunAsync(messages, thread, options, cancellationToken);

    /// <inheritdoc/>
    public sealed override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
        base.RunStreamingAsync(messages, thread, options, cancellationToken);
}
