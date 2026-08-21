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

try
{
    await foreach (AgentResponseUpdate update in remoteAgent.RunStreamingAsync(
        new ChatMessage(ChatRole.User, "Review this proposal."),
        remoteSession))
    {
        switch (update.AsChatResponseUpdate().RawRepresentation)
        {
            case StepStartedEvent started:
                Console.WriteLine($"\n[Step started: {started.StepName}]");
                break;
            case StepFinishedEvent finished:
                Console.WriteLine($"\n[Step finished: {finished.StepName}]");
                break;
        }

        foreach (TextContent text in update.Contents.OfType<TextContent>())
        {
            Console.Write(text.Text);
        }
    }
}
catch (InvalidOperationException exception)
{
    Console.WriteLine($"\n[Known nested-step identity limitation (#7763): {exception.Message}]");
}

Console.WriteLine();
