// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Runtime.CompilerServices;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace AgentWebChat.Web;

/// <summary>
/// Is a simple frontend client which exercises the ability of exposed agent to communicate via OpenAI ChatCompletions protocol.
/// </summary>
internal sealed class OpenAIChatCompletionsAgentClient(HttpClient httpClient) : AgentClientBase
{
    public async override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string agentName,
        IList<ChatMessage> messages,
        string? threadId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        OpenAIClientOptions options = new()
        {
            Endpoint = new Uri(httpClient.BaseAddress!, $"/{agentName}/v1/"),
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        var openAiClient = new ChatClient(model: "myModel!", credential: new ApiKeyCredential("dummy-key"), options: options).AsIChatClient();
        await foreach (var update in openAiClient.GetStreamingResponseAsync(messages, cancellationToken: cancellationToken))
        {
            yield return new AgentRunResponseUpdate(update);
        }
    }
}
