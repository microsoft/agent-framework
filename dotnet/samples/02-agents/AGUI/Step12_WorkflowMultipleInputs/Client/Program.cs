// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";
using HttpClient httpClient = new() { Timeout = TimeSpan.FromSeconds(60) };
using IChatClient chatClient = CreateChatClient(httpClient, serverUrl);

List<ChatResponseUpdate> firstTurn = await chatClient
    .GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Plan my conference trip.")])
    .ToListAsync();
RunFinishedEvent firstFinished = firstTurn.Select(static update => update.RawRepresentation)
    .OfType<RunFinishedEvent>()
    .Single();
AGUIInterrupt[] requests = [.. ((RunFinishedInterruptOutcome)firstFinished.Outcome!).Interrupts];

AGUIInterrupt dates = requests.Single(static item => item.Message!.Contains("TravelDates"));
AGUIInterrupt travelers = requests.Single(static item => item.Message!.Contains("TravelerDetails"));
AGUIInterrupt preferences = requests.Single(static item => item.Message!.Contains("TravelPreferences"));

List<ChatResponseUpdate> partialTurn = await chatClient.GetStreamingResponseAsync(
    [],
    CreateResumeOptions(
        firstFinished,
        [
            Resume(travelers, new { kind = "travelers", count = 2, accessibility = "none" }),
            Resume(dates, new { kind = "dates", departure = "2026-10-10", returnDate = "2026-10-14" }),
        ])).ToListAsync();
RunFinishedEvent partialFinished = partialTurn.Select(static update => update.RawRepresentation)
    .OfType<RunFinishedEvent>()
    .Single();

List<ChatResponseUpdate> finalTurn = await chatClient.GetStreamingResponseAsync(
    [],
    CreateResumeOptions(
        partialFinished,
        [Resume(preferences, new { kind = "preferences", budget = 2500, cabin = "economy", hotel = "downtown" })]))
    .ToListAsync();

Console.WriteLine(string.Concat(finalTurn.Select(static update => update.Text)));

ChatOptions CreateResumeOptions(RunFinishedEvent previous, IList<AGUIResume> resumes)
    => new()
    {
        RawRepresentationFactory = _ => new RunAgentInput
        {
            Messages = [],
            ParentRunId = previous.RunId,
            Resume = resumes,
            RunId = Guid.NewGuid().ToString("N"),
            ThreadId = previous.ThreadId,
        },
    };

static AGUIResume Resume(AGUIInterrupt interrupt, object payload)
    => new()
    {
        InterruptId = interrupt.Id,
        Payload = JsonSerializer.SerializeToElement(payload),
        Status = "resolved",
    };

static IChatClient CreateChatClient(HttpClient httpClient, string serverUrl)
    => new AGUIChatClient(new(httpClient, serverUrl));
