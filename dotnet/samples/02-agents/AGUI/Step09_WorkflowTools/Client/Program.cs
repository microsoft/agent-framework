// Copyright (c) Microsoft. All rights reserved.

using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
using IChatClient chatClient = CreateChatClient(httpClient, serverUrl);

await foreach (ChatResponseUpdate update in chatClient.GetStreamingResponseAsync(
    [new ChatMessage(ChatRole.User, "What is the weather in Seattle?")]))
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

    foreach (AIContent content in update.Contents)
    {
        switch (content)
        {
            case FunctionCallContent call:
                Console.WriteLine($"\n[Tool call: {call.Name}]");
                break;
            case FunctionResultContent result:
                Console.WriteLine($"\n[Tool result: {result.Result}]");
                break;
            case TextContent text:
                Console.Write(text.Text);
                break;
        }
    }
}

Console.WriteLine();

static IChatClient CreateChatClient(HttpClient httpClient, string serverUrl)
    => new AGUIChatClient(new(httpClient, serverUrl));
