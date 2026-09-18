// Copyright (c) Microsoft. All rights reserved.

// Client for the local_responses_workflow server sample. Like the agent client, it shows the two idiomatic
// ways to consume an OpenAI Responses endpoint from .NET, both pointed at the same workflow route (written in the paired Server):
//
//   1. CC  - a plain Microsoft.Extensions.AI IChatClient (the lower-level chat-client path).
//   2. MAF - a Microsoft Agent Framework AIAgent + AgentSession (the higher-level agent path).
//
// The server implements previous_response_id continuation only (it rejects conversation-id continuity), so
// both paths follow the rotating response-id chain: the first turn sends a JSON brief, the follow-up turn
// continues from the first turn's response id. The workflow resumes its checkpoint across that chain.

using System.ClientModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

string serverUrl = Environment.GetEnvironmentVariable("RESPONSES_SERVER_URL") ?? "http://localhost:5001";
string model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

const string Brief = """{ "topic": "electric SUV", "style": "playful", "audience": "young families" }""";
const string FollowUp = "Make it a little more premium, but still family friendly.";

ResponsesClient responseClient = new OpenAIClient(
        new ApiKeyCredential("not-needed"),
        new OpenAIClientOptions { Endpoint = new Uri(serverUrl) })
    .GetResponsesClient();

Console.WriteLine($"Connecting to {serverUrl}\n");

await RunWithChatClientAsync(responseClient, model).ConfigureAwait(false);
await RunWithAgentAsync(responseClient, model).ConfigureAwait(false);

// CC path: consume the endpoint through a Microsoft.Extensions.AI IChatClient. Continuity is threaded by
// hand: each response's ChatResponse.ConversationId (a "resp_" id) is passed back as the next turn's
// ChatOptions.ConversationId, which the SDK sends as previous_response_id.
static async Task RunWithChatClientAsync(ResponsesClient responseClient, string model)
{
    Console.WriteLine("== CC: Microsoft.Extensions.AI IChatClient ==");
    IChatClient chatClient = responseClient.AsIChatClient(model);

    Console.WriteLine($"User: {Brief}");
    ChatResponse first = await chatClient.GetResponseAsync(Brief).ConfigureAwait(false);
    Console.WriteLine($"Workflow: {first.Text}\n");

    Console.WriteLine($"User: {FollowUp}");
    ChatResponse second = await chatClient.GetResponseAsync(
        FollowUp,
        new ChatOptions { ConversationId = first.ConversationId }).ConfigureAwait(false);
    Console.WriteLine($"Workflow: {second.Text}\n");
}

// MAF path: consume the same endpoint through an Agent Framework AIAgent. A single AgentSession threads the
// rotating previous_response_id chain automatically, so the caller only sends the new input each turn.
static async Task RunWithAgentAsync(ResponsesClient responseClient, string model)
{
    Console.WriteLine("== MAF: Agent Framework AIAgent + AgentSession ==");
    AIAgent agent = responseClient.AsAIAgent(model: model, name: "HostedWorkflowClient");
    AgentSession session = await agent.CreateSessionAsync().ConfigureAwait(false);

    Console.WriteLine($"User: {Brief}");
    AgentResponse first = await agent.RunAsync(Brief, session).ConfigureAwait(false);
    Console.WriteLine($"Workflow: {first.Text}\n");

    Console.WriteLine($"User: {FollowUp}");
    AgentResponse second = await agent.RunAsync(FollowUp, session).ConfigureAwait(false);
    Console.WriteLine($"Workflow: {second.Text}\n");
}
