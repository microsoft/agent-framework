// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to dynamically expand the set of function tools available to an
// agent during a function-calling loop. The agent starts with a single "RequestTools" function.
// When the model calls RequestTools with a description of the capabilities needed, the function
// uses the ambient FunctionInvocationContext to add new tools to ChatOptions.Tools. The agent
// can then use the newly added tools in subsequent iterations of the same function-calling loop.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// Pre-defined tool implementations that can be loaded on demand.
[Description("Get the current weather for a city.")]
static string GetWeather([Description("The city name.")] string city) =>
    city.ToUpperInvariant() switch
    {
        "SEATTLE" => "Seattle: 55°F, cloudy with light rain.",
        "NEW YORK" => "New York: 72°F, sunny and warm.",
        "LONDON" => "London: 48°F, overcast with fog.",
        _ => $"{city}: weather data not available, please provide one of the following city names: 'Seattle', 'New York', 'London'."
    };

[Description("Get the current local time for a city.")]
static string GetTime([Description("The city name.")] string city) =>
    city.ToUpperInvariant() switch
    {
        "SEATTLE" => "Seattle: 9:00 AM PST",
        "NEW YORK" => "New York: 12:00 PM EST",
        "LONDON" => "London: 5:00 PM GMT",
        _ => $"{city}: time data not available, please provide one of the following city names: 'Seattle', 'New York', 'London'."
    };

[Description("Convert a temperature from Fahrenheit to Celsius.")]
static string ConvertFahrenheitToCelsius([Description("The temperature in Fahrenheit.")] double fahrenheit) =>
    $"{fahrenheit}°F = {(fahrenheit - 32) * 5 / 9:F1}°C";

// A registry of tool sets that can be loaded by description keyword.
Dictionary<string, List<AITool>> toolCatalog = new(StringComparer.OrdinalIgnoreCase)
{
    ["weather"] = [AIFunctionFactory.Create(GetWeather, name: "GetWeather")],
    ["time"] = [AIFunctionFactory.Create(GetTime, name: "GetTime")],
    ["temperature"] = [AIFunctionFactory.Create(ConvertFahrenheitToCelsius, name: "ConvertFahrenheitToCelsius")],
};

// The RequestTools function uses the ambient FunctionInvocationContext to add tools dynamically.
AIFunction requestToolsFunction = AIFunctionFactory.Create(
    [Description("Request additional tools to be loaded based on a description of the functionality needed. " +
                 "Call this when you need capabilities that are not yet available in your current tool set.")] (
        [Description("A description of the functionality required, e.g. 'weather', 'time', or 'temperature conversion'.")] string description
    ) =>
    {
        // Access the ambient FunctionInvocationContext provided by FunctionInvokingChatClient.
        var context = FunctionInvokingChatClient.CurrentContext
            ?? throw new InvalidOperationException("No ambient FunctionInvocationContext available.");

        var tools = context.Options?.Tools;
        if (tools is null)
        {
            return "Unable to register new tools: ChatOptions.Tools is not available.";
        }

        // Find matching tool sets from the catalog.
        List<string> addedToolNames = [];
        foreach (var kvp in toolCatalog)
        {
            var keyword = kvp.Key;
            var catalogTools = kvp.Value;
            if (description.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            {
                foreach (var tool in catalogTools)
                {
                    // Avoid adding duplicates.
                    if (tool is AIFunction fn && !tools.Any(t => t is AIFunction existing && existing.Name == fn.Name))
                    {
                        tools.Add(tool);
                        addedToolNames.Add(fn.Name);
                    }
                }
            }
        }

        return addedToolNames.Count > 0
            ? "Successfully loaded tools"
            : $"No tools matched the description '{description}'. Available categories: {string.Join(", ", toolCatalog.Keys)}.";
    },
    name: "RequestTools");

// Create the agent with only the RequestTools function initially.
// Insert chat client middleware that logs the tools available on each LLM call,
// making the dynamic expansion visible in the console output.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .AsBuilder()
    .Use(getResponseFunc: ToolLoggingMiddleware, getStreamingResponseFunc: ToolLoggingStreamingMiddleware)
    .BuildAIAgent(
        instructions: """
            You are a helpful assistant. You start with limited tools.
            When you need functionality that you don't currently have, call RequestTools with a description
            of what you need. After new tools are loaded, use them to answer the user's question.
            """,
        tools: [requestToolsFunction]);

// Run a conversation that triggers dynamic tool expansion.
Console.WriteLine("=== Dynamic Function Tools Sample ===\n");

string[] prompts =
[
    "What's the weather like in Seattle and London?",
    "What time is it in New York?",
    "Can you convert those temperatures to Celsius?"
];

// --- Non-Streaming Mode ---
Console.ForegroundColor = ConsoleColor.Yellow;
Console.WriteLine("=== Non-Streaming Mode ===");
Console.ResetColor();
Console.WriteLine();

AgentSession session = await agent.CreateSessionAsync();

foreach (var prompt in prompts)
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.Write("[User] ");
    Console.ResetColor();
    Console.WriteLine(prompt);

    var response = await agent.RunAsync(prompt, session);

    // Print all message contents including tool calls, tool results, and text.
    foreach (var message in response.Messages)
    {
        foreach (var content in message.Contents)
        {
            switch (content)
            {
                case FunctionCallContent functionCall:
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine($"  [Tool Call] {functionCall.Name}({string.Join(", ", functionCall.Arguments?.Select(a => $"{a.Key}: {a.Value}") ?? [])})");
                    Console.ResetColor();
                    break;

                case FunctionResultContent functionResult:
                    Console.ForegroundColor = ConsoleColor.DarkYellow;
                    Console.WriteLine($"  [Tool Result] {functionResult.CallId} => {functionResult.Result}");
                    Console.ResetColor();
                    break;

                case TextContent textContent when !string.IsNullOrWhiteSpace(textContent.Text):
                    Console.ForegroundColor = ConsoleColor.Cyan;
                    Console.Write("[Agent] ");
                    Console.ResetColor();
                    Console.WriteLine(textContent.Text);
                    break;
            }
        }
    }

    Console.WriteLine();
}

// --- Streaming Mode ---
Console.ForegroundColor = ConsoleColor.Yellow;
Console.WriteLine("=== Streaming Mode ===");
Console.ResetColor();
Console.WriteLine();

AgentSession streamingSession = await agent.CreateSessionAsync();

foreach (var prompt in prompts)
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.Write("[User] ");
    Console.ResetColor();
    Console.WriteLine(prompt);

    bool inAgentText = false;

    await foreach (var update in agent.RunStreamingAsync(prompt, streamingSession))
    {
        foreach (var content in update.Contents)
        {
            switch (content)
            {
                case FunctionCallContent functionCall:
                    if (inAgentText)
                    {
                        Console.WriteLine();
                        inAgentText = false;
                    }

                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine($"  [Tool Call] {functionCall.Name}({string.Join(", ", functionCall.Arguments?.Select(a => $"{a.Key}: {a.Value}") ?? [])})");
                    Console.ResetColor();
                    break;

                case FunctionResultContent functionResult:
                    Console.ForegroundColor = ConsoleColor.DarkYellow;
                    Console.WriteLine($"  [Tool Result] {functionResult.CallId} => {functionResult.Result}");
                    Console.ResetColor();
                    break;

                case TextContent textContent when !string.IsNullOrWhiteSpace(textContent.Text):
                    if (!inAgentText)
                    {
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.Write("[Agent] ");
                        Console.ResetColor();
                        inAgentText = true;
                    }

                    Console.Write(textContent.Text);
                    break;
            }
        }
    }

    if (inAgentText)
    {
        Console.WriteLine();
    }

    Console.WriteLine();
}

// Chat client middleware that logs the number and names of tools on each LLM request.
async Task<ChatResponse> ToolLoggingMiddleware(
    IEnumerable<ChatMessage> messages,
    ChatOptions? options,
    IChatClient innerChatClient,
    CancellationToken cancellationToken)
{
    LogTools(options);

    return await innerChatClient.GetResponseAsync(messages, options, cancellationToken);
}

// Streaming version of the tool logging middleware.
async IAsyncEnumerable<ChatResponseUpdate> ToolLoggingStreamingMiddleware(
    IEnumerable<ChatMessage> messages,
    ChatOptions? options,
    IChatClient innerChatClient,
    [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
{
    LogTools(options);

    await foreach (var update in innerChatClient.GetStreamingResponseAsync(messages, options, cancellationToken))
    {
        yield return update;
    }
}

// Shared helper to log the current tool set.
void LogTools(ChatOptions? options)
{
    if (options?.Tools is { Count: > 0 } tools)
    {
        var toolNames = tools.OfType<AIFunction>().Select(t => t.Name);
        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine($"  [Middleware] LLM call with {tools.Count} tool(s): {string.Join(", ", toolNames)}");
        Console.ResetColor();
    }
    else
    {
        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine("  [Middleware] LLM call with 0 tools");
        Console.ResetColor();
    }
}
