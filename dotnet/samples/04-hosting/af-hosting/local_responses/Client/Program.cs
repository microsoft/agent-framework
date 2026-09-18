// Copyright (c) Microsoft. All rights reserved.

// Client for the HostingResponsesAgent server sample. It shows the two idiomatic ways to consume an
// OpenAI Responses endpoint from .NET, both pointed at the same server route (written in the paired Server):
//
//   1. CC  - a plain Microsoft.Extensions.AI IChatClient (the lower-level chat-client path).
//   2. MAF - a Microsoft Agent Framework AIAgent + AgentSession (the higher-level agent path).
//
// Both run the same three-turn conversation. The third turn only makes sense if the server remembered
// the first turn, so it also proves multi-turn session continuity across the rotating response-id chain.

using System.ClientModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

string serverUrl = Environment.GetEnvironmentVariable("RESPONSES_SERVER_URL") ?? "http://localhost:5000";

// The server ignores the model id (it runs its own configured agent), but the OpenAI SDK requires one to
// shape the request. Reuse FOUNDRY_MODEL for parity with the server sample.
string model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

string[] prompts =
[
    "What is the weather in Tokyo?",
    "And what about Amsterdam?",
    "Which of the two cities we just discussed is warmer?",
];

// A single ResponsesClient pointed at the local server backs both consumption paths. The api key is unused
// by the sample server, but the SDK requires a credential.
ResponsesClient responseClient = new OpenAIClient(
        new ApiKeyCredential("not-needed"),
        new OpenAIClientOptions { Endpoint = new Uri(serverUrl) })
    .GetResponsesClient();

Console.WriteLine($"Connecting to {serverUrl}\n");

await RunWithChatClientAsync(responseClient, model, prompts).ConfigureAwait(false);
await RunWithAgentAsync(responseClient, model, prompts).ConfigureAwait(false);

// CC path: consume the endpoint through a Microsoft.Extensions.AI IChatClient. Continuity is threaded by
// hand: each response carries the server's response id as ChatResponse.ConversationId, which we pass back
// as the next turn's ChatOptions.ConversationId. Because it is a "resp_" id, the SDK sends it as
// previous_response_id, exactly what the server's GetSessionStoreId reads.
static async Task RunWithChatClientAsync(ResponsesClient responseClient, string model, string[] prompts)
{
    Console.WriteLine("== CC: Microsoft.Extensions.AI IChatClient ==");
    IChatClient chatClient = responseClient.AsIChatClient(model);

    string? previousResponseId = null;
    foreach (string prompt in prompts)
    {
        Console.WriteLine($"User: {prompt}");
        ChatResponse response = await chatClient.GetResponseAsync(
            prompt,
            new ChatOptions { ConversationId = previousResponseId }).ConfigureAwait(false);
        Console.WriteLine($"Agent: {response.Text}");
        previousResponseId = response.ConversationId;
        Console.WriteLine($"Response ID: {previousResponseId}\n");
    }
}

// MAF path: consume the same endpoint through an Agent Framework AIAgent. A single AgentSession threads the
// rotating response-id chain automatically, so the caller only sends the new user message each turn.
static async Task RunWithAgentAsync(ResponsesClient responseClient, string model, string[] prompts)
{
    Console.WriteLine("== MAF: Agent Framework AIAgent + AgentSession ==");
    AIAgent agent = responseClient.AsAIAgent(model: model, name: "HostedResponsesClient");
    AgentSession session = await agent.CreateSessionAsync().ConfigureAwait(false);

    foreach (string prompt in prompts)
    {
        Console.WriteLine($"User: {prompt}");
        AgentResponse response = await agent.RunAsync(prompt, session).ConfigureAwait(false);
        Console.WriteLine($"Agent: {response.Text}\n");
    }
}
