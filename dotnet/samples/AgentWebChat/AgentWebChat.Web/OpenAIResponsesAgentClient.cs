// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Runtime.CompilerServices;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

namespace AgentWebChat.Web;

/// <summary>
/// Is a simple frontend client which exercises the ability of exposed agent to communicate via OpenAI Responses protocol.
/// </summary>
internal sealed class OpenAIResponsesAgentClient(HttpClient httpClient) : AgentClientBase
{
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string agentName,
        IList<ChatMessage> messages,
        string? threadId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        OpenAIClientOptions options = new()
        {
            Endpoint = new Uri(httpClient.BaseAddress!, "/v1/"),
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        var openAiClient = new OpenAIResponseClient(model: agentName, credential: new ApiKeyCredential("dummy-key"), options: options).AsIChatClient();
        var chatOptions = new ChatOptions()
        {
            ConversationId = threadId
        };

        await foreach (var update in openAiClient.GetStreamingResponseAsync(messages, chatOptions, cancellationToken: cancellationToken))
        {
            yield return new AgentRunResponseUpdate(update);
        }
    }
}
