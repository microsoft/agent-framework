// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how the ChatClientAgent persists chat history after each individual
// call to the AI service, using the RequirePerServiceCallChatHistoryPersistence option.
// When an agent uses tools, FunctionInvokingChatClient may loop multiple times
// (service call → tool execution → service call), and intermediate messages (tool calls and
// results) are persisted after each service call. This allows you to inspect or recover them
// even if the process is interrupted mid-loop, but may also result in chat history that is not
// yet finalized (e.g., tool calls without results) being persisted, which may be undesirable in some cases.
//
// To use end-of-run persistence instead (atomic run semantics), remove the
// RequirePerServiceCallChatHistoryPersistence = true setting (or set it to false). End-of-run
// persistence is the default behavior.
//
// The sample runs two multi-turn conversations: one using non-streaming (RunAsync) and one
// using streaming (RunStreamingAsync), to demonstrate correct behavior in both modes.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
var store = Environment.GetEnvironmentVariable("AZURE_OPENAI_RESPONSES_STORE") ?? "false";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AzureOpenAIClient openAIClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Define multiple tools so the model makes several tool calls in a single run.
[Description("Get the current weather for a city.")]
static string GetWeather([Description("The city name.")] string city) =>
    city.ToUpperInvariant() switch
    {
        "SEATTLE" => "Seattle: 55°F, cloudy with light rain.",
        "NEW YORK" => "New York: 72°F, sunny and warm.",
        "LONDON" => "London: 48°F, overcast with fog.",
        "DUBLIN" => "Dublin: 43°F, overcast with fog.",
        _ => $"{city}: weather data not available."
    };

[Description("Get the current time in a city.")]
static string GetTime([Description("The city name.")] string city) =>
    city.ToUpperInvariant() switch
    {
        "SEATTLE" => "Seattle: 9:00 AM PST",
        "NEW YORK" => "New York: 12:00 PM EST",
        "LONDON" => "London: 5:00 PM GMT",
        "DUBLIN" => "Dublin: 5:00 PM GMT",
        _ => $"{city}: time data not available."
    };

// Create the agent — per-service-call persistence is enabled via RequirePerServiceCallChatHistoryPersistence.
// The in-memory ChatHistoryProvider is used by default when the service does not require service stored chat
// history, so for those cases, we can inspect the chat history via session.TryGetInMemoryChatHistory().
IChatClient chatClient = string.Equals(store, "TRUE", StringComparison.OrdinalIgnoreCase) ?
    openAIClient.GetResponsesClient().AsIChatClient(deploymentName) :
    openAIClient.GetResponsesClient().AsIChatClientWithStoredOutputDisabled(deploymentName);
AIAgent agent = chatClient.AsAIAgent(
    new ChatClientAgentOptions
    {
        Name = "WeatherAssistant",
        RequirePerServiceCallChatHistoryPersistence = true,
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant. When asked about multiple cities, call the appropriate tool for each city.",
            Tools = [AIFunctionFactory.Create(GetWeather), AIFunctionFactory.Create(GetTime)]
        },
    });

await RunNonStreamingAsync();
await RunStreamingAsync();

async Task RunNonStreamingAsync()
{
    int lastChatHistorySize = 0;
    string lastConversationId = string.Empty;

    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine("\n=== Non-Streaming Mode ===");
    Console.ResetColor();

    AgentSession session = await agent.CreateSessionAsync();

    // First turn — ask about multiple cities so the model calls tools.
    const string Prompt = "What's the weather and time in Seattle, New York, and London?";
    PrintUserMessage(Prompt);

    var response = await agent.RunAsync(Prompt, session);
    PrintAgentResponse(response.Text);
    PrintChatHistory(session, "After run", ref lastChatHistorySize, ref lastConversationId);

    // Second turn — follow-up to verify chat history is correct.
    const string FollowUp1 = "And Dublin?";
    PrintUserMessage(FollowUp1);

    response = await agent.RunAsync(FollowUp1, session);
    PrintAgentResponse(response.Text);
    PrintChatHistory(session, "After second run", ref lastChatHistorySize, ref lastConversationId);

    // Third turn — follow-up to verify chat history is correct.
    const string FollowUp2 = "Which city is the warmest?";
    PrintUserMessage(FollowUp2);

    response = await agent.RunAsync(FollowUp2, session);
    PrintAgentResponse(response.Text);
    PrintChatHistory(session, "After third run", ref lastChatHistorySize, ref lastConversationId);
}

async Task RunStreamingAsync()
{
    int lastChatHistorySize = 0;
    string lastConversationId = string.Empty;

    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine("\n=== Streaming Mode ===");
    Console.ResetColor();

    AgentSession session = await agent.CreateSessionAsync();

    // First turn — ask about multiple cities so the model calls tools.
    const string Prompt = "What's the weather and time in Seattle, New York, and London?";
    PrintUserMessage(Prompt);

    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.Write("\n[Agent] ");
    Console.ResetColor();

    await foreach (var update in agent.RunStreamingAsync(Prompt, session))
    {
        Console.Write(update);

        // During streaming we should be able to see updates to the chat history
        // before the full run completes, as each service call is made and persisted.
        PrintChatHistory(session, "During run", ref lastChatHistorySize, ref lastConversationId);
    }

    Console.WriteLine();
    PrintChatHistory(session, "After run", ref lastChatHistorySize, ref lastConversationId);

    // Second turn — follow-up to verify chat history is correct.
    const string FollowUp1 = "And Dublin?";
    PrintUserMessage(FollowUp1);

    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.Write("\n[Agent] ");
    Console.ResetColor();

    await foreach (var update in agent.RunStreamingAsync(FollowUp1, session))
    {
        Console.Write(update);

        // During streaming we should be able to see updates to the chat history
        // before the full run completes, as each service call is made and persisted.
        PrintChatHistory(session, "During second run", ref lastChatHistorySize, ref lastConversationId);
    }

    Console.WriteLine();
    PrintChatHistory(session, "After second run", ref lastChatHistorySize, ref lastConversationId);

    // Third turn — follow-up to verify chat history is correct.
    const string FollowUp2 = "Which city is the warmest?";
    PrintUserMessage(FollowUp2);

    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.Write("\n[Agent] ");
    Console.ResetColor();

    await foreach (var update in agent.RunStreamingAsync(FollowUp2, session))
    {
        Console.Write(update);

        // During streaming we should be able to see updates to the chat history
        // before the full run completes, as each service call is made and persisted.
        PrintChatHistory(session, "During third run", ref lastChatHistorySize, ref lastConversationId);
    }

    Console.WriteLine();
    PrintChatHistory(session, "After third run", ref lastChatHistorySize, ref lastConversationId);
}

void PrintUserMessage(string message)
{
    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.Write("\n[User] ");
    Console.ResetColor();
    Console.WriteLine(message);
}

void PrintAgentResponse(string? text)
{
    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.Write("\n[Agent] ");
    Console.ResetColor();
    Console.WriteLine(text);
}

// Helper to print the current chat history from the session.
void PrintChatHistory(AgentSession session, string label, ref int lastChatHistorySize, ref string lastConversationId)
{
    if (session.TryGetInMemoryChatHistory(out var history) && history.Count != lastChatHistorySize)
    {
        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine($"\n  [{label} — Chat history: {history.Count} message(s)]");
        foreach (var msg in history)
        {
            var preview = msg.Text?.Length > 80 ? msg.Text[..80] + "…" : msg.Text;
            var contentTypes = string.Join(", ", msg.Contents.Select(c => c.GetType().Name));
            Console.WriteLine($"    {msg.Role,-12} | {(string.IsNullOrWhiteSpace(preview) ? $"[{contentTypes}]" : preview)}");
        }

        Console.ResetColor();

        lastChatHistorySize = history.Count;
    }

    if (session is ChatClientAgentSession ccaSession && ccaSession.ConversationId is not null && ccaSession.ConversationId != lastConversationId)
    {
        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine($"  [{label} — Conversation ID: {ccaSession.ConversationId}]");
        Console.ResetColor();
        lastConversationId = ccaSession.ConversationId;
    }
}
