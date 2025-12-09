// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AGUI;
using Microsoft.Extensions.AI;
using RecipeClient;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";

Console.WriteLine($"Connecting to AG-UI server at: {serverUrl}\n");

// Create the AG-UI client agent
using HttpClient httpClient = new()
{
    Timeout = TimeSpan.FromSeconds(60)
};

AGUIChatClient chatClient = new(httpClient, serverUrl);

AIAgent baseAgent = chatClient.CreateAIAgent(
    name: "recipe-client",
    description: "AG-UI Recipe Client Agent");

// Wrap the base agent with state management
JsonSerializerOptions jsonOptions = new(JsonSerializerDefaults.Web)
{
    TypeInfoResolver = RecipeSerializerContext.Default
};
StatefulAgent<AgentState> agent = new(baseAgent, jsonOptions, new AgentState());

AgentThread thread = agent.GetNewThread();
List<ChatMessage> messages =
[
    new(ChatRole.System, "You are a helpful recipe assistant.")
];

try
{
    while (true)
    {
        // Get user input
        Console.Write("\nUser (:q to quit, :state to show state): ");
        string? message = Console.ReadLine();

        if (string.IsNullOrWhiteSpace(message))
        {
            Console.WriteLine("Request cannot be empty.");
            continue;
        }

        if (message is ":q" or "quit")
        {
            break;
        }

        if (message.Equals(":state", StringComparison.OrdinalIgnoreCase))
        {
            DisplayState(agent.State.Recipe);
            continue;
        }

        messages.Add(new ChatMessage(ChatRole.User, message));

        // Stream the response
        bool isFirstUpdate = true;
        string? threadId = null;
        bool stateReceived = false;

        Console.WriteLine();

        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, thread))
        {
            ChatResponseUpdate chatUpdate = update.AsChatResponseUpdate();

            // First update indicates run started
            if (isFirstUpdate)
            {
                threadId = chatUpdate.ConversationId;
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine($"[Run Started - Thread: {chatUpdate.ConversationId}, Run: {chatUpdate.ResponseId}]");
                Console.ResetColor();
                isFirstUpdate = false;
            }

            // Display streaming content
            foreach (AIContent content in update.Contents)
            {
                switch (content)
                {
                    case TextContent textContent:
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.Write(textContent.Text);
                        Console.ResetColor();
                        break;

                    case DataContent dataContent when dataContent.MediaType == "application/json":
                        // This is a state snapshot - the StatefulAgent has already updated the state
                        stateReceived = true;
                        Console.ForegroundColor = ConsoleColor.Blue;
                        Console.WriteLine("\n[State Snapshot Received]");
                        Console.ResetColor();
                        break;

                    case ErrorContent errorContent:
                        Console.ForegroundColor = ConsoleColor.Red;
                        Console.WriteLine($"\n[Error: {errorContent.Message}]");
                        Console.ResetColor();
                        break;
                }
            }
        }

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"\n[Run Finished - Thread: {threadId}]");
        Console.ResetColor();

        // Display final state if received
        if (stateReceived)
        {
            DisplayState(agent.State.Recipe);
        }
    }
}
catch (Exception ex)
{
    Console.WriteLine($"\nAn error occurred: {ex.Message}");
}

static void DisplayState(RecipeState? state)
{
    if (state == null)
    {
        Console.ForegroundColor = ConsoleColor.Gray;
        Console.WriteLine("\n[No state available]");
        Console.ResetColor();
        return;
    }

    Console.ForegroundColor = ConsoleColor.Blue;
    Console.WriteLine("\n" + new string('=', 60));
    Console.WriteLine("CURRENT STATE");
    Console.WriteLine(new string('=', 60));
    Console.ResetColor();

    if (!string.IsNullOrEmpty(state.Title))
    {
        Console.WriteLine("\nRecipe:");
        Console.WriteLine($"  Title: {state.Title}");
        if (!string.IsNullOrEmpty(state.Cuisine))
        {
            Console.WriteLine($"  Cuisine: {state.Cuisine}");
        }

        if (!string.IsNullOrEmpty(state.SkillLevel))
        {
            Console.WriteLine($"  Skill Level: {state.SkillLevel}");
        }

        if (state.PrepTimeMinutes > 0)
        {
            Console.WriteLine($"  Prep Time: {state.PrepTimeMinutes} minutes");
        }

        if (state.CookTimeMinutes > 0)
        {
            Console.WriteLine($"  Cook Time: {state.CookTimeMinutes} minutes");
        }

        if (state.Ingredients.Count > 0)
        {
            Console.WriteLine("\n  Ingredients:");
            foreach (var ingredient in state.Ingredients)
            {
                Console.WriteLine($"    - {ingredient}");
            }
        }

        if (state.Steps.Count > 0)
        {
            Console.WriteLine("\n  Steps:");
            for (int i = 0; i < state.Steps.Count; i++)
            {
                Console.WriteLine($"    {i + 1}. {state.Steps[i]}");
            }
        }
    }

    Console.ForegroundColor = ConsoleColor.Blue;
    Console.WriteLine("\n" + new string('=', 60));
    Console.ResetColor();
}

// State wrapper
internal sealed class AgentState
{
    [JsonPropertyName("recipe")]
    public RecipeState Recipe { get; set; } = new();
}

// Recipe state model
internal sealed class RecipeState
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("cuisine")]
    public string Cuisine { get; set; } = string.Empty;

    [JsonPropertyName("ingredients")]
    public List<string> Ingredients { get; set; } = [];

    [JsonPropertyName("steps")]
    public List<string> Steps { get; set; } = [];

    [JsonPropertyName("prep_time_minutes")]
    public int PrepTimeMinutes { get; set; }

    [JsonPropertyName("cook_time_minutes")]
    public int CookTimeMinutes { get; set; }

    [JsonPropertyName("skill_level")]
    public string SkillLevel { get; set; } = string.Empty;
}

// JSON serialization context
[JsonSerializable(typeof(AgentState))]
[JsonSerializable(typeof(RecipeState))]
[JsonSerializable(typeof(JsonElement))]
internal sealed partial class RecipeSerializerContext : JsonSerializerContext;
