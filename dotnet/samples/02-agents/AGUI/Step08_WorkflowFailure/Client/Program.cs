// Copyright (c) Microsoft. All rights reserved.

using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
using IChatClient chatClient = CreateChatClient(httpClient, serverUrl);

await foreach (ChatResponseUpdate update in chatClient.GetStreamingResponseAsync(
    [new ChatMessage(ChatRole.User, "Run the failing workflow.")]))
{
    switch (update.RawRepresentation)
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

static IChatClient CreateChatClient(HttpClient httpClient, string serverUrl)
    => new AGUIChatClient(new(httpClient, serverUrl));
