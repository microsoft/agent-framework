// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
using IChatClient chatClient = new AGUIChatClient(new(httpClient, serverUrl));

List<ChatResponseUpdate> firstTurn = await chatClient
    .GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Submit expense EXP-100.")])
    .ToListAsync();
RunFinishedEvent finished = firstTurn.Select(static update => update.RawRepresentation)
    .OfType<RunFinishedEvent>()
    .Single();
AGUIInterrupt interrupt = ((RunFinishedInterruptOutcome)finished.Outcome!).Interrupts.Single();

Console.Write($"{interrupt.Message ?? "Approve expense?"} [y/N]: ");
bool approved = string.Equals(Console.ReadLine(), "y", StringComparison.OrdinalIgnoreCase);

ChatOptions resumeOptions = new()
{
    RawRepresentationFactory = _ => new RunAgentInput
    {
        Messages = [],
        ParentRunId = finished.RunId,
        Resume =
        [
            new AGUIResume
            {
                InterruptId = interrupt.Id,
                Payload = JsonSerializer.SerializeToElement(new { approved }),
                Status = "resolved",
            },
        ],
        RunId = Guid.NewGuid().ToString("N"),
        ThreadId = finished.ThreadId,
    },
};

List<ChatResponseUpdate> secondTurn = await chatClient
    .GetStreamingResponseAsync([], resumeOptions)
    .ToListAsync();
Console.WriteLine(string.Concat(secondTurn.Select(static update => update.Text)));
