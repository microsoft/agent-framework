// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to implement reliable streaming for durable agents using Redis Streams.
// It reads prompts from stdin and streams agent responses to stdout in real-time.

using System.ComponentModel;
using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenAI.Chat;
using ReliableStreaming;
using StackExchange.Redis;

// Get the Azure OpenAI endpoint and deployment name from environment variables.
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Get Redis connection string from environment variable.
string redisConnectionString = Environment.GetEnvironmentVariable("REDIS_CONNECTION_STRING")
    ?? "localhost:6379";

// Get the Redis stream TTL from environment variable (default: 10 minutes).
int redisStreamTtlMinutes = int.Parse(Environment.GetEnvironmentVariable("REDIS_STREAM_TTL_MINUTES") ?? "10");

// Get DTS connection string from environment variable
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
string? azureOpenAiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY");
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential());

// Travel Planner agent instructions - designed to produce longer responses for demonstrating streaming.
const string TravelPlannerName = "TravelPlanner";
const string TravelPlannerInstructions =
    """
    You are an expert travel planner who creates detailed, personalized travel itineraries.
    When asked to plan a trip, you should:
    1. Create a comprehensive day-by-day itinerary
    2. Include specific recommendations for activities, restaurants, and attractions
    3. Provide practical tips for each destination
    4. Consider weather and local events when making recommendations
    5. Include estimated times and logistics between activities
    
    Always use the available tools to get current weather forecasts and local events
    for the destination to make your recommendations more relevant and timely.
    
    Format your response with clear headings for each day and include emoji icons
    to make the itinerary easy to scan and visually appealing.
    """;

// Mock travel tools that return hardcoded data for demonstration purposes.
[Description("Gets the weather forecast for a destination on a specific date. Use this to provide weather-aware recommendations in the itinerary.")]
static string GetWeatherForecast(string destination, string date)
{
    Dictionary<string, (string condition, int highF, int lowF)> weatherByRegion = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Tokyo"] = ("Partly cloudy with a chance of light rain", 58, 45),
        ["Paris"] = ("Overcast with occasional drizzle", 52, 41),
        ["New York"] = ("Clear and cold", 42, 28),
        ["London"] = ("Foggy morning, clearing in afternoon", 48, 38),
        ["Sydney"] = ("Sunny and warm", 82, 68),
        ["Rome"] = ("Sunny with light breeze", 62, 48),
        ["Barcelona"] = ("Partly sunny", 59, 47),
        ["Amsterdam"] = ("Cloudy with light rain", 46, 38),
        ["Dubai"] = ("Sunny and hot", 85, 72),
        ["Singapore"] = ("Tropical thunderstorms in afternoon", 88, 77),
        ["Bangkok"] = ("Hot and humid, afternoon showers", 91, 78),
        ["Los Angeles"] = ("Sunny and pleasant", 72, 55),
        ["San Francisco"] = ("Morning fog, afternoon sun", 62, 52),
        ["Seattle"] = ("Rainy with breaks", 48, 40),
        ["Miami"] = ("Warm and sunny", 78, 65),
        ["Honolulu"] = ("Tropical paradise weather", 82, 72),
    };

    (string condition, int highF, int lowF) forecast = ("Partly cloudy", 65, 50);
    foreach (KeyValuePair<string, (string, int, int)> entry in weatherByRegion)
    {
        if (destination.Contains(entry.Key, StringComparison.OrdinalIgnoreCase))
        {
            forecast = entry.Value;
            break;
        }
    }

    return $"""
        Weather forecast for {destination} on {date}:
        Conditions: {forecast.condition}
        High: {forecast.highF}°F ({(forecast.highF - 32) * 5 / 9}°C)
        Low: {forecast.lowF}°F ({(forecast.lowF - 32) * 5 / 9}°C)
        
        Recommendation: {GetWeatherRecommendation(forecast.condition)}
        """;
}

[Description("Gets local events and activities happening at a destination around a specific date. Use this to suggest timely activities and experiences.")]
static string GetLocalEvents(string destination, string date)
{
    Dictionary<string, string[]> eventsByCity = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Tokyo"] = [
            "🎭 Kabuki Theater Performance at Kabukiza Theatre - Traditional Japanese drama",
            "🌸 Winter Illuminations at Yoyogi Park - Spectacular light displays",
            "🍜 Ramen Festival at Tokyo Station - Sample ramen from across Japan",
            "🎮 Gaming Expo at Tokyo Big Sight - Latest video games and technology",
        ],
        ["Paris"] = [
            "🎨 Impressionist Exhibition at Musée d'Orsay - Extended evening hours",
            "🍷 Wine Tasting Tour in Le Marais - Local sommelier guided",
            "🎵 Jazz Night at Le Caveau de la Huchette - Historic jazz club",
            "🥐 French Pastry Workshop - Learn from master pâtissiers",
        ],
        ["New York"] = [
            "🎭 Broadway Show: Hamilton - Limited engagement performances",
            "🏀 Knicks vs Lakers at Madison Square Garden",
            "🎨 Modern Art Exhibit at MoMA - New installations",
            "🍕 Pizza Walking Tour of Brooklyn - Artisan pizzerias",
        ],
        ["London"] = [
            "👑 Royal Collection Exhibition at Buckingham Palace",
            "🎭 West End Musical: The Phantom of the Opera",
            "🍺 Craft Beer Festival at Brick Lane",
            "🎪 Winter Wonderland at Hyde Park - Rides and markets",
        ],
        ["Sydney"] = [
            "🏄 Pro Surfing Competition at Bondi Beach",
            "🎵 Opera at Sydney Opera House - La Bohème",
            "🦘 Wildlife Night Safari at Taronga Zoo",
            "🍽️ Harbor Dinner Cruise with fireworks",
        ],
        ["Rome"] = [
            "🏛️ After-Hours Vatican Tour - Skip the crowds",
            "🍝 Pasta Making Class in Trastevere",
            "🎵 Classical Concert at Borghese Gallery",
            "🍷 Wine Tasting in Roman Cellars",
        ],
    };

    string[] events = [
        "🎭 Local theater performance",
        "🍽️ Food and wine festival",
        "🎨 Art gallery opening",
        "🎵 Live music at local venues",
    ];

    foreach (KeyValuePair<string, string[]> entry in eventsByCity)
    {
        if (destination.Contains(entry.Key, StringComparison.OrdinalIgnoreCase))
        {
            events = entry.Value;
            break;
        }
    }

    string eventList = string.Join("\n• ", events);
    return $"""
        Local events in {destination} around {date}:
        
        • {eventList}
        
        💡 Tip: Book popular events in advance as they may sell out quickly!
        """;
}

static string GetWeatherRecommendation(string condition)
{
    return condition switch
    {
        string c when c.Contains("rain", StringComparison.OrdinalIgnoreCase) || c.Contains("drizzle", StringComparison.OrdinalIgnoreCase) =>
            "Bring an umbrella and waterproof jacket. Consider indoor activities for backup.",
        string c when c.Contains("fog", StringComparison.OrdinalIgnoreCase) =>
            "Morning visibility may be limited. Plan outdoor sightseeing for afternoon.",
        string c when c.Contains("cold", StringComparison.OrdinalIgnoreCase) =>
            "Layer up with warm clothing. Hot drinks and cozy cafés recommended.",
        string c when c.Contains("hot", StringComparison.OrdinalIgnoreCase) || c.Contains("warm", StringComparison.OrdinalIgnoreCase) =>
            "Stay hydrated and use sunscreen. Plan strenuous activities for cooler morning hours.",
        string c when c.Contains("thunder", StringComparison.OrdinalIgnoreCase) || c.Contains("storm", StringComparison.OrdinalIgnoreCase) =>
            "Keep an eye on weather updates. Have indoor alternatives ready.",
        _ => "Pleasant conditions expected. Great day for outdoor exploration!"
    };
}

// Configure the console app to host the AI agent.
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(loggingBuilder => loggingBuilder.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableAgents(
            options =>
            {
                // Define the Travel Planner agent with tools for weather and events
                options.AddAIAgentFactory(TravelPlannerName, sp =>
                {
                    return client.GetChatClient(deploymentName).AsAIAgent(
                        instructions: TravelPlannerInstructions,
                        name: TravelPlannerName,
                        services: sp,
                        tools: [
                            AIFunctionFactory.Create(GetWeatherForecast),
                            AIFunctionFactory.Create(GetLocalEvents),
                        ]);
                });
            },
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));

        // Register Redis connection as a singleton
        services.AddSingleton<IConnectionMultiplexer>(_ =>
            ConnectionMultiplexer.Connect(redisConnectionString));

        // Register the Redis stream response handler - this captures agent responses
        // and publishes them to Redis Streams for reliable delivery.
        services.AddSingleton(sp =>
            new RedisStreamResponseHandler(
                sp.GetRequiredService<IConnectionMultiplexer>(),
                TimeSpan.FromMinutes(redisStreamTtlMinutes)));
        services.AddSingleton<IAgentResponseHandler>(sp =>
            sp.GetRequiredService<RedisStreamResponseHandler>());
    })
    .Build();

await host.StartAsync();

// Get the agent proxy from services
IServiceProvider services = host.Services;
AIAgent? agentProxy = services.GetKeyedService<AIAgent>(TravelPlannerName);
RedisStreamResponseHandler streamHandler = services.GetRequiredService<RedisStreamResponseHandler>();

if (agentProxy == null)
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.Error.WriteLine($"Agent '{TravelPlannerName}' not found.");
    Console.ResetColor();
    Environment.Exit(1);
    return;
}

// Console colors for better UX
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("=== Reliable Streaming Sample ===");
Console.ResetColor();
Console.WriteLine("Enter a travel planning request (or 'exit' to quit):");
Console.WriteLine();

string? lastCursor = null;

async Task ReadStreamTask(string conversationId, string? cursor, CancellationToken cancellationToken)
{
    // Initialize lastCursor to the starting cursor position
    // This ensures we have a valid cursor even if cancellation happens before any chunks are processed
    lastCursor = cursor;

    await foreach (StreamChunk chunk in streamHandler.ReadStreamAsync(conversationId, cursor, cancellationToken))
    {
        if (chunk.Error != null)
        {
            Console.ForegroundColor = ConsoleColor.Red;
            Console.Error.WriteLine($"\n[Error: {chunk.Error}]");
            Console.ResetColor();
            break;
        }

        if (chunk.IsDone)
        {
            Console.WriteLine();
            Console.WriteLine();
            break;
        }

        if (chunk.Text != null)
        {
            Console.Write(chunk.Text);
        }

        // Always update lastCursor to track the latest entry ID, even if text is null
        // This ensures we can resume from the correct position after interruption
        if (!string.IsNullOrEmpty(chunk.EntryId))
        {
            lastCursor = chunk.EntryId;
        }
    }
}

// New conversation: prompt from stdin
Console.ForegroundColor = ConsoleColor.Yellow;
Console.Write("You: ");
Console.ResetColor();

string? prompt = Console.ReadLine();
if (string.IsNullOrWhiteSpace(prompt) || prompt.Equals("exit", StringComparison.OrdinalIgnoreCase))
{
    return;
}

// Create a new agent session
AgentSession session = await agentProxy.CreateSessionAsync();
AgentSessionId sessionId = session.GetService<AgentSessionId>();
string conversationId = sessionId.ToString();

Console.ForegroundColor = ConsoleColor.Green;
Console.WriteLine($"Conversation ID: {conversationId}");
Console.WriteLine("Press [Enter] to interrupt the stream.");
Console.ResetColor();

// Run the agent in the background
DurableAgentRunOptions options = new() { IsFireAndForget = true };
await agentProxy.RunAsync(prompt, session, options, CancellationToken.None);

bool streamCompleted = false;
while (!streamCompleted)
{
    // On a key press, cancel the cancellation token to stop the stream
    using CancellationTokenSource userCancellationSource = new();
    _ = Task.Run(() =>
    {
        _ = Console.ReadLine();
        userCancellationSource.Cancel();
    });

    try
    {
        // Start reading the stream and wait for it to complete
        await ReadStreamTask(conversationId, lastCursor, userCancellationSource.Token);
        streamCompleted = true;
    }
    catch (OperationCanceledException)
    {
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine("Stream cancelled. Press [Enter] to reconnect and resume the stream from the last cursor.");
        // Ensure lastCursor is set - if it's still null, we at least have the starting cursor
        string cursorValue = lastCursor ?? "(n/a)";
        Console.WriteLine($"Last cursor: {cursorValue}");
        Console.ResetColor();
        // Explicitly flush to ensure the message is written immediately
        Console.Out.Flush();
    }

    if (!streamCompleted)
    {
        Console.ReadLine();
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"Resuming conversation: {conversationId} from cursor: {lastCursor ?? "(beginning)"}");
        Console.ResetColor();
    }
}

Console.ForegroundColor = ConsoleColor.Green;
Console.WriteLine("Conversation completed.");
Console.ResetColor();

await host.StopAsync();
