// Copyright (c) Microsoft. All rights reserved.

using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
using IChatClient chatClient = CreateChatClient(httpClient, serverUrl);

Console.Write("Request: ");
string request = Console.ReadLine() ?? "Write a short welcome message for a developer conference.";

await foreach (ChatResponseUpdate update in chatClient.GetStreamingResponseAsync(
    [new ChatMessage(ChatRole.User, request)]))
{
    switch (update.RawRepresentation)
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

Console.WriteLine();

static IChatClient CreateChatClient(HttpClient httpClient, string serverUrl)
    => new AGUIChatClient(new(httpClient, serverUrl));
