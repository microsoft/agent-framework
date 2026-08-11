// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using RecipeClient;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";

Console.WriteLine($"Connecting to AG-UI server at: {serverUrl}\n");

// Create the AG-UI client agent
using HttpClient httpClient = new()
{
    Timeout = TimeSpan.FromSeconds(60)
};

AGUIChatClient chatClient = new(new(httpClient, serverUrl));

AIAgent agent = chatClient.AsAIAgent(
    name: "recipe-client",
    description: "AG-UI Recipe Client Agent");

JsonSerializerOptions jsonOptions = RecipeSerializerContext.Default.Options;

// The recipe lives on the client. It is sent to the server on every turn (so the agent edits the
// existing recipe) and refreshed from each STATE_SNAPSHOT the server streams back.
Recipe currentRecipe = new();

AgentSession session = await agent.CreateSessionAsync();
List<ChatMessage> messages =
[
    new(ChatRole.System, "You are a helpful recipe assistant.")
];

try
{
    while (true)
    {
        // Get user input
        Console.Write("\nUser (:q to quit, :state to show recipe): ");
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
            DisplayRecipe(currentRecipe);
            continue;
        }

        messages.Add(new ChatMessage(ChatRole.User, message));

        // Send the client's current recipe on the AG-UI RunAgentInput.State so the agent builds on it.
        JsonElement stateJson = JsonSerializer.SerializeToElement(
            new RecipeResponse { Recipe = currentRecipe }, jsonOptions);
        ChatClientAgentRunOptions runOptions = new()
        {
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = _ => new RunAgentInput { State = stateJson }
            }
        };

        // Stream the response
        bool isFirstUpdate = true;
        Console.WriteLine();

        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(messages, session, runOptions))
        {
            ChatResponseUpdate chatUpdate = update.AsChatResponseUpdate();

            // First update indicates run started
            if (isFirstUpdate)
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine($"[Run Started - Run: {chatUpdate.ResponseId}]");
                Console.ResetColor();
                isFirstUpdate = false;
            }

            // A STATE_SNAPSHOT arrives as a StateSnapshotEvent on the update's raw representation.
            if (chatUpdate.RawRepresentation is StateSnapshotEvent snapshot &&
                snapshot.Snapshot.Deserialize<RecipeResponse>(jsonOptions) is { } response)
            {
                currentRecipe = response.Recipe;
                Console.ForegroundColor = ConsoleColor.Blue;
                Console.WriteLine("\n[State Snapshot Received]");
                Console.ResetColor();
            }

            // Display streaming text content
            foreach (AIContent content in update.Contents)
            {
                switch (content)
                {
                    case TextContent textContent:
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.Write(textContent.Text);
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

        // The session owns prior history, so the next run sends only the new user message.
        messages.Clear();

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine("\n[Run Finished]");
        Console.ResetColor();

        DisplayRecipe(currentRecipe);
    }
}
catch (Exception ex)
{
    Console.WriteLine($"\nAn error occurred: {ex.Message}");
}

static void DisplayRecipe(Recipe recipe)
{
    Console.ForegroundColor = ConsoleColor.Blue;
    Console.WriteLine("\n" + new string('=', 60));
    Console.WriteLine("CURRENT RECIPE");
    Console.WriteLine(new string('=', 60));
    Console.ResetColor();

    if (string.IsNullOrEmpty(recipe.Title))
    {
        Console.ForegroundColor = ConsoleColor.Gray;
        Console.WriteLine("\n[No recipe yet]");
        Console.ResetColor();
    }
    else
    {
        Console.WriteLine($"\n  Title: {recipe.Title}");
        if (!string.IsNullOrEmpty(recipe.SkillLevel))
        {
            Console.WriteLine($"  Skill Level: {recipe.SkillLevel}");
        }

        if (!string.IsNullOrEmpty(recipe.CookingTime))
        {
            Console.WriteLine($"  Cooking Time: {recipe.CookingTime}");
        }

        if (recipe.SpecialPreferences.Count > 0)
        {
            Console.WriteLine($"  Preferences: {string.Join(", ", recipe.SpecialPreferences)}");
        }

        if (recipe.Ingredients.Count > 0)
        {
            Console.WriteLine("\n  Ingredients:");
            foreach (Ingredient ingredient in recipe.Ingredients)
            {
                Console.WriteLine($"    {ingredient.Icon} {ingredient.Name} - {ingredient.Amount}");
            }
        }

        if (recipe.Instructions.Count > 0)
        {
            Console.WriteLine("\n  Instructions:");
            for (int i = 0; i < recipe.Instructions.Count; i++)
            {
                Console.WriteLine($"    {i + 1}. {recipe.Instructions[i]}");
            }
        }
    }

    Console.ForegroundColor = ConsoleColor.Blue;
    Console.WriteLine("\n" + new string('=', 60));
    Console.ResetColor();
}

namespace RecipeClient
{
    // State response wrapper. Its shape mirrors what the server returns and renders as state.
    internal sealed class RecipeResponse
    {
        [JsonPropertyName("recipe")]
        public Recipe Recipe { get; set; } = new();
    }

    // Recipe state model.
    internal sealed class Recipe
    {
        [JsonPropertyName("title")]
        public string Title { get; set; } = string.Empty;

        [JsonPropertyName("skill_level")]
        public string SkillLevel { get; set; } = string.Empty;

        [JsonPropertyName("cooking_time")]
        public string CookingTime { get; set; } = string.Empty;

        [JsonPropertyName("special_preferences")]
        public List<string> SpecialPreferences { get; set; } = [];

        [JsonPropertyName("ingredients")]
        public List<Ingredient> Ingredients { get; set; } = [];

        [JsonPropertyName("instructions")]
        public List<string> Instructions { get; set; } = [];
    }

    // A single ingredient.
    internal sealed class Ingredient
    {
        [JsonPropertyName("icon")]
        public string Icon { get; set; } = string.Empty;

        [JsonPropertyName("name")]
        public string Name { get; set; } = string.Empty;

        [JsonPropertyName("amount")]
        public string Amount { get; set; } = string.Empty;
    }

    // JSON serialization context.
    [JsonSerializable(typeof(RecipeResponse))]
    [JsonSerializable(typeof(Recipe))]
    [JsonSerializable(typeof(Ingredient))]
    internal sealed partial class RecipeSerializerContext : JsonSerializerContext;
}
