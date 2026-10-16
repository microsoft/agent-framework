// Copyright (c) Microsoft. All rights reserved.

using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
using IChatClient chatClient = CreateChatClient(httpClient, serverUrl);

try
{
    await foreach (ChatResponseUpdate update in chatClient.GetStreamingResponseAsync(
        [new ChatMessage(ChatRole.User, "Review this proposal.")]))
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
}
catch (InvalidOperationException exception)
{
    Console.WriteLine($"\n[Known nested-step identity limitation (#7763): {exception.Message}]");
}

Console.WriteLine();

static IChatClient CreateChatClient(HttpClient httpClient, string serverUrl)
    => new AGUIChatClient(new(httpClient, serverUrl));
