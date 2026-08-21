// Copyright (c) Microsoft. All rights reserved.

using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
AGUIChatClient chatClient = new(new(httpClient, serverUrl));
AIAgent agent = chatClient.AsAIAgent(name: "workflow-client");
AgentSession session = await agent.CreateSessionAsync();

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(
    new ChatMessage(ChatRole.User, "Run the failing workflow."),
    session))
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
