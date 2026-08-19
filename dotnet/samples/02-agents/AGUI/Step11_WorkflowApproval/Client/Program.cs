// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http.Json;
using System.Text.Json;
using AGUI.Abstractions;
using AGUI.Client;
using AGUI.Server;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { BaseAddress = new Uri(serverUrl), Timeout = TimeSpan.FromSeconds(60) };

RunAgentInput initialInput = new()
{
    Messages = new[] { new ChatMessage(ChatRole.User, "Submit expense EXP-100.") }.AsAGUIMessages().ToList(),
    RunId = Guid.NewGuid().ToString("N"),
    ThreadId = Guid.NewGuid().ToString("N"),
};
List<BaseEvent> firstTurn = await SendAsync(initialInput);
RunFinishedEvent finished = firstTurn.OfType<RunFinishedEvent>().Single();
AGUIInterrupt interrupt = ((RunFinishedInterruptOutcome)finished.Outcome!).Interrupts.Single();

Console.Write($"{interrupt.Message ?? "Approve expense?"} [y/N]: ");
bool approved = string.Equals(Console.ReadLine(), "y", StringComparison.OrdinalIgnoreCase);

RunAgentInput resumeInput = new()
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
};

List<BaseEvent> secondTurn = await SendAsync(resumeInput);
Console.WriteLine(string.Concat(secondTurn.OfType<TextMessageContentEvent>().Select(static evt => evt.Delta)));

async Task<List<BaseEvent>> SendAsync(RunAgentInput input)
{
    using JsonContent content = JsonContent.Create(input, AGUIJsonSerializerContext.Default.RunAgentInput);
    using HttpResponseMessage response = await httpClient.PostAsync(new Uri("", UriKind.Relative), content);
    response.EnsureSuccessStatusCode();
    return await response.ReadAGUIEventStreamAsync().ToListAsync();
}
