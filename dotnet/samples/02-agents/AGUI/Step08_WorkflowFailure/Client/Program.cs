// Copyright (c) Microsoft. All rights reserved.

using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
AGUIChatClient chatClient = new(new(httpClient, serverUrl));
AIAgent remoteAgent = chatClient.AsAIAgent(name: "workflow-client");
AgentSession remoteSession = await remoteAgent.CreateSessionAsync();

await foreach (AgentResponseUpdate update in remoteAgent.RunStreamingAsync(
    new ChatMessage(ChatRole.User, "Run the failing workflow."),
    remoteSession))
{
    switch (update.AsChatResponseUpdate().RawRepresentation)
    {
        case StepStartedEvent started:
            Console.WriteLine($"[Step started: {started.StepName}]");
            break;
        case StepFinishedEvent finished:
            Console.WriteLine($"[Step finished: {finished.StepName}]");
            break;
        case RunErrorEvent error:
            Console.WriteLine($"[Error: {error.Message}]");
            break;
    }
}
