// Copyright (c) Microsoft. All rights reserved.

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

    public OpenAIChatClientAgent(OpenAIClient client, string model, string? instructions = null, string? name = null, string? description = null, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(model);

        var chatClient = client.GetChatClient(model).AsIChatClient();
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

    public OpenAIChatClientAgent(OpenAIClient client, string model, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(model);

        var chatClient = client.GetChatClient(model).AsIChatClient();
        this._chatClientAgent = new(chatClient, options, loggerFactory);
    }

    public async Task<ChatCompletion> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var response = await this.RunAsync([.. messages.AsChatMessages()], thread, options, cancellationToken);

        var chatCompletion = response.AsChatCompletion();
        return chatCompletion;
    }

    /// <inheritdoc/>
    public override AgentThread GetNewThread()
    {
        return this._chatClientAgent.GetNewThread();
    }

    /// <inheritdoc/>
    public override Task<AgentRunResponse> RunAsync(IReadOnlyCollection<Microsoft.Extensions.AI.ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this._chatClientAgent.RunAsync(messages, thread, options, cancellationToken);
    }

    /// <inheritdoc/>
    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IReadOnlyCollection<Microsoft.Extensions.AI.ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return this._chatClientAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
    }
}
