// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Chat;
using ChatMessage = OpenAI.Chat.ChatMessage;

namespace OpenAI;

/// <summary>
/// OpenAI chat completion based implementation of <see cref="AIAgent"/>.
/// </summary>
public class OpenAIChatClientAgent : AIAgent
{
    private readonly ChatClientAgent _chatClientAgent;

    /// <summary>
    /// Initialize an instance of <see cref="OpenAIChatClientAgent"/>
    /// </summary>
    /// <param name="client">Instance of <see cref="ChatClient"/></param>
    /// <param name="instructions">Optional instructions for the agent.</param>
    /// <param name="name">Optional name for the agent.</param>
    /// <param name="description">Optional description for the agent.</param>
    /// <param name="loggerFactory">Optional instance of <see cref="ILoggerFactory"/></param>
    public OpenAIChatClientAgent(
        ChatClient client,
        string? instructions = null,
        string? name = null,
        string? description = null,
        ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);

        var chatClient = client.AsIChatClient();
        this._chatClientAgent = new(
            chatClient,
            new ChatClientAgentOptions()
            {
                Name = name,
                Description = description,
                Instructions = instructions,
            },
            loggerFactory);
    }

    /// <summary>
    /// Initialize an instance of <see cref="OpenAIChatClientAgent"/>
    /// </summary>
    /// <param name="client">Instance of <see cref="ChatClient"/></param>
    /// <param name="options">Options to create the agent.</param>
    /// <param name="loggerFactory">Optional instance of <see cref="ILoggerFactory"/></param>
    public OpenAIChatClientAgent(ChatClient client, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);

        var chatClient = client.AsIChatClient();
        this._chatClientAgent = new(chatClient, options, loggerFactory);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent response.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatCompletion"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public virtual async Task<ChatCompletion> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var response = await this.RunAsync([.. messages.AsChatMessages()], thread, options, cancellationToken).ConfigureAwait(false);

        return response.AsChatCompletion();
    }

    /// <inheritdoc/>
    public sealed override AgentThread GetNewThread()
        => this._chatClientAgent.GetNewThread();

    /// <inheritdoc/>
    public sealed override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => this._chatClientAgent.DeserializeThread(serializedThread, jsonSerializerOptions);

    /// <inheritdoc/>
    public sealed override Task<AgentRunResponse> RunAsync(
        IEnumerable<Microsoft.Extensions.AI.ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
            => this._chatClientAgent.RunAsync(messages, thread, options, cancellationToken);

    /// <inheritdoc/>
    public sealed override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<Microsoft.Extensions.AI.ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
            => this._chatClientAgent.RunStreamingAsync(messages, thread, options, cancellationToken);

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
        => base.GetService(serviceType, serviceKey)
        ?? this._chatClientAgent.GetService(serviceType, serviceKey);
}
