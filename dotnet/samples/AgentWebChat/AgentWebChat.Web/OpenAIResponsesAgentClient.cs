// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Runtime.CompilerServices;
using A2A;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

namespace AgentWebChat.Web;

/// <summary>
/// Is a simple frontend client which exercises the ability of exposed agent to communicate via OpenAI Responses protocol.
/// </summary>
#pragma warning disable CA1812 // created via DI
internal sealed class OpenAIResponsesAgentClient : IAgentClient
#pragma warning restore CA1812 // created via DI
{
    private readonly HttpClient _httpClient;

    public OpenAIResponsesAgentClient(HttpClient httpClient)
    {
        this._httpClient = httpClient;
    }

    public async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string agentName,
        IList<ChatMessage> messages,
        string? threadId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        OpenAIClientOptions options = new()
        {
            Endpoint = new Uri(this._httpClient.BaseAddress!, $"/{agentName}/v1/"),
            Transport = new HttpClientPipelineTransport(this._httpClient)
        };

        var openAiClient = new OpenAIResponseClient(model: "myModel!", credential: new ApiKeyCredential("dummy-key"), options: options).AsIChatClient();
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
