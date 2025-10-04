// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Runtime.CompilerServices;
using A2A;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

namespace AgentWebChat.Web;

internal sealed class OpenAIResponsesAgentClient : IAgentClient
{
    private readonly Uri _baseUri;

    public OpenAIResponsesAgentClient(string baseUri)
    {
        this._baseUri = new Uri(baseUri.TrimEnd('/'));
    }

    public async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string agentName,
        IList<ChatMessage> messages,
        string? threadId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // this is a "root" of the OpenAI Responses surface for the agent
        var relativeUri = "/" + agentName + "/v1/";

        OpenAIClientOptions options = new()
        {
            Endpoint = new Uri(this._baseUri, relativeUri)
        };

        OpenAIResponseClient openAiClient = new(model: "myModel!", credential: new ApiKeyCredential("dummy-key"), options: options);
        var chatClient = openAiClient.AsIChatClient();
        var chatOptions = new ChatOptions()
        {
            ConversationId = threadId
        };

        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, chatOptions, cancellationToken: cancellationToken))
        {
            yield return new AgentRunResponseUpdate(update);
        }
    }

    public Task<AgentCard?> GetAgentCardAsync(string agentName, CancellationToken cancellationToken = default)
        => Task.FromResult<AgentCard?>(null!);
}
