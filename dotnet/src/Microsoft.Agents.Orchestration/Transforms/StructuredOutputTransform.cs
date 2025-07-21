// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Populates the target result type  <see cref="ChatMessage"/> into a structured output.
/// </summary>
/// <typeparam name="TOutput">The .NET type of the structured-output to deserialization target.</typeparam>
public sealed class StructuredOutputTransform<TOutput>
{
    internal const string DefaultInstructions = "Respond with JSON that is populated by using the information in this conversation.";

    private readonly IChatClient _client;
    private readonly ChatOptions? _options;

    /// <summary>
    /// Initializes a new instance of the <see cref="StructuredOutputTransform{TOutput}"/> class.
    /// </summary>
    /// <param name="client">The chat completion service to use for generating responses.</param>
    /// <param name="chatOptions">The prompt execution settings to use for the chat completion service.</param>
    public StructuredOutputTransform(IChatClient client, ChatOptions? chatOptions = null)
    {
        Throw.IfNull(client, nameof(client));

        this._client = client;
        this._options = chatOptions;
    }

    /// <summary>
    /// Gets or sets the instructions to be used as the system message for the chat completion.
    /// </summary>
    public string Instructions { get; init; } = DefaultInstructions;

    /// <summary>
    /// Transforms the provided <see cref="ChatMessage"/> into a strongly-typed structured output by invoking the chat completion service and deserializing the response.
    /// </summary>
    /// <param name="messages">The chat messages to process.</param>
    /// <param name="serializerOptions">The JSON serializer options to use when performing any JSON serialization.</param>
    /// <param name="cancellationToken">A cancellation token to observe while waiting for the task to complete.</param>
    /// <returns>The structured output of type <typeparamref name="TOutput"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the response cannot be deserialized into <typeparamref name="TOutput"/>.</exception>
    public async ValueTask<TOutput> TransformAsync(IList<ChatMessage> messages, JsonSerializerOptions? serializerOptions = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        ChatResponse<TOutput> response = await this._client.GetResponseAsync<TOutput>(
            [
                new ChatMessage(ChatRole.System, this.Instructions),
                .. messages,
            ],
            serializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions,
            this._options,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        return response.Result;
    }
}
