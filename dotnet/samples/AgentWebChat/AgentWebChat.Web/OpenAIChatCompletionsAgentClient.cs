// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Runtime.CompilerServices;
using A2A;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace AgentWebChat.Web;

/// <summary>
/// Is a simple frontend client which exercises the ability of exposed agent to communicate via OpenAI ChatCompletions protocol.
/// </summary>
internal sealed class OpenAIChatCompletionsAgentClient : IAgentClient
{
    private readonly Uri _baseUri;

    public OpenAIChatCompletionsAgentClient(string baseUri)
    {
        this._baseUri = new Uri(baseUri.TrimEnd('/'));
    }

    public async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string agentName,
        IList<ChatMessage> messages,
        string? threadId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        OpenAIClientOptions options = new()
        {
            Endpoint = new Uri(this._baseUri, $"/{agentName}/v1/")
        };

        var openAiClient = new ChatClient(model: "myModel!", credential: new ApiKeyCredential("dummy-key"), options: options).AsIChatClient();
        var chatOptions = new ChatOptions()
        {
            ConversationId = threadId
        };

        await foreach (var update in openAiClient.GetStreamingResponseAsync(messages, chatOptions, cancellationToken: cancellationToken))
        {
            yield return new AgentRunResponseUpdate(update);
        }
    }

    public Task<AgentCard?> GetAgentCardAsync(string agentName, CancellationToken cancellationToken = default)
        => Task.FromResult<AgentCard?>(null!);
}
