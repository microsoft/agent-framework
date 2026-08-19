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
    Messages = new[] { new ChatMessage(ChatRole.User, "Plan my conference trip.") }.AsAGUIMessages().ToList(),
    RunId = Guid.NewGuid().ToString("N"),
    ThreadId = Guid.NewGuid().ToString("N"),
};
List<BaseEvent> firstTurn = await SendAsync(initialInput);
RunFinishedEvent firstFinished = firstTurn.OfType<RunFinishedEvent>().Single();
AGUIInterrupt[] requests = [.. ((RunFinishedInterruptOutcome)firstFinished.Outcome!).Interrupts];

AGUIInterrupt dates = requests.Single(static item => item.Message!.Contains("TravelDates"));
AGUIInterrupt travelers = requests.Single(static item => item.Message!.Contains("TravelerDetails"));
AGUIInterrupt preferences = requests.Single(static item => item.Message!.Contains("TravelPreferences"));

RunFinishedEvent partialFinished = (await SendAsync(CreateResume(
    firstFinished,
    [
        Resume(travelers, new { kind = "travelers", count = 2, accessibility = "none" }),
        Resume(dates, new { kind = "dates", departure = "2026-10-10", returnDate = "2026-10-14" }),
    ]))).OfType<RunFinishedEvent>().Single();

List<BaseEvent> finalTurn = await SendAsync(CreateResume(
    partialFinished,
    [Resume(preferences, new { kind = "preferences", budget = 2500, cabin = "economy", hotel = "downtown" })]));

Console.WriteLine(string.Concat(finalTurn.OfType<TextMessageContentEvent>().Select(static evt => evt.Delta)));

RunAgentInput CreateResume(RunFinishedEvent previous, IList<AGUIResume> resumes)
    => new()
    {
        Messages = [],
        ParentRunId = previous.RunId,
        Resume = resumes,
        RunId = Guid.NewGuid().ToString("N"),
        ThreadId = previous.ThreadId,
    };

static AGUIResume Resume(AGUIInterrupt interrupt, object payload)
    => new()
    {
        InterruptId = interrupt.Id,
        Payload = JsonSerializer.SerializeToElement(payload),
        Status = "resolved",
    };

async Task<List<BaseEvent>> SendAsync(RunAgentInput input)
{
    using JsonContent content = JsonContent.Create(input, AGUIJsonSerializerContext.Default.RunAgentInput);
    using HttpResponseMessage response = await httpClient.PostAsync(new Uri("", UriKind.Relative), content);
    response.EnsureSuccessStatusCode();
    return await response.ReadAGUIEventStreamAsync().ToListAsync();
}
