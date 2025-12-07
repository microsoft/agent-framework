// Copyright (c) Microsoft. All rights reserved.

// This sample shows multiple middleware layers working together with Azure Foundry Agents:
// agent run (PII filtering and guardrails),
// function invocation (logging and result overrides), and human-in-the-loop
// approval workflows for sensitive function calls.

using System.ComponentModel;
using System.Text.RegularExpressions;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

// Get Azure AI Foundry configuration from environment variables
string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = System.Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o";

const string AssistantInstructions = "You are an AI assistant that helps people find information.";
const string AssistantName = "InformationAssistant";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

[Description("The current datetime offset.")]
static string GetDateTime()
    => DateTimeOffset.Now.ToString();

AITool dateTimeTool = AIFunctionFactory.Create(GetDateTime, name: nameof(GetDateTime));
AITool getWeatherTool = AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather));

// Define the agent you want to create. (Prompt Agent in this case)
AIAgent originalAgent = aiProjectClient.CreateAIAgent(
    name: AssistantName,
    model: deploymentName,
    instructions: AssistantInstructions,
    tools: [getWeatherTool, dateTimeTool]);

// Adding middleware to the agent level
AIAgent middlewareEnabledAgent = originalAgent
    .AsBuilder()
    .Use(FunctionCallMiddleware)
    .Use(FunctionCallOverrideWeather)
    .Use(PIIMiddleware, null)
    .Use(GuardrailMiddleware, null)
    .Build();

AgentThread thread = middlewareEnabledAgent.GetNewThread();

Console.WriteLine("\n\n=== Example 1: Wording Guardrail ===");
AgentRunResponse guardRailedResponse = await middlewareEnabledAgent.RunAsync("Tell me something harmful.");
Console.WriteLine($"Guard railed response: {guardRailedResponse}");

Console.WriteLine("\n\n=== Example 2: PII detection ===");
AgentRunResponse piiResponse = await middlewareEnabledAgent.RunAsync("My name is John Doe, call me at 123-456-7890 or email me at john@something.com");
Console.WriteLine($"Pii filtered response: {piiResponse}");

Console.WriteLine("\n\n=== Example 3: Agent function middleware ===");

// Agent function middleware support is limited to agents that wraps a upstream ChatClientAgent or derived from it.

AgentRunResponse functionCallResponse = await middlewareEnabledAgent.RunAsync("What's the current time and the weather in Seattle?", thread);
Console.WriteLine($"Function calling response: {functionCallResponse}");

// Special per-request middleware agent.
Console.WriteLine("\n\n=== Example 4: Middleware with human in the loop function approval ===");

AIAgent humanInTheLoopAgent = aiProjectClient.CreateAIAgent(
    name: "HumanInTheLoopAgent",
    model: deploymentName,
    instructions: "You are an Human in the loop testing AI assistant that helps people find information.",

    // Adding a function with approval required
    tools: [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather)))]);

// Using the ConsolePromptingApprovalMiddleware for a specific request to handle user approval during function calls.
AgentRunResponse response = await humanInTheLoopAgent
    .AsBuilder()
    .Use(ConsolePromptingApprovalMiddleware, null)
    .Build()
    .RunAsync("What's the current time and the weather in Seattle?");

Console.WriteLine($"HumanInTheLoopAgent agent middleware response: {response}");

// Function invocation middleware that logs before and after function calls.
async ValueTask<object?> FunctionCallMiddleware(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
{
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 1 Pre-Invoke");
    var result = await next(context, cancellationToken);
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 1 Post-Invoke");

    return result;
}

// Function invocation middleware that overrides the result of the GetWeather function.
async ValueTask<object?> FunctionCallOverrideWeather(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
{
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 2 Pre-Invoke");

    var result = await next(context, cancellationToken);

    if (context.Function.Name == nameof(GetWeather))
    {
        // Override the result of the GetWeather function
        result = "The weather is sunny with a high of 25°C.";
    }
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 2 Post-Invoke");
    return result;
}

// This middleware redacts PII information from input and output messages.
async Task<AgentRunResponse> PIIMiddleware(IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    // Redact PII information from input messages
    var filteredMessages = FilterMessages(messages);
    Console.WriteLine("Pii Middleware - Filtered Messages Pre-Run");

    var response = await innerAgent.RunAsync(filteredMessages, thread, options, cancellationToken).ConfigureAwait(false);

    // Redact PII information from output messages
    response.Messages = FilterMessages(response.Messages);

    Console.WriteLine("Pii Middleware - Filtered Messages Post-Run");

    return response;

    static IList<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
    }

    static string FilterPii(string content)
    {
        // Regex patterns for PII detection (simplified for demonstration)
        Regex[] piiPatterns = [
            new(@"\b\d{3}-\d{3}-\d{4}\b", RegexOptions.Compiled), // Phone number (e.g., 123-456-7890)
                    new(@"\b[\w\.-]+@[\w\.-]+\.\w+\b", RegexOptions.Compiled), // Email address
                    new(@"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", RegexOptions.Compiled) // Full name (e.g., John Doe)
        ];

        foreach (var pattern in piiPatterns)
        {
            content = pattern.Replace(content, "[REDACTED: PII]");
        }

        return content;
    }
}

// This middleware enforces guardrails by redacting certain keywords from input and output messages.
async Task<AgentRunResponse> GuardrailMiddleware(IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    // Redact keywords from input messages
    var filteredMessages = FilterMessages(messages);

    Console.WriteLine("Guardrail Middleware - Filtered messages Pre-Run");

    // Proceed with the agent run
    var response = await innerAgent.RunAsync(filteredMessages, thread, options, cancellationToken);

    // Redact keywords from output messages
    response.Messages = FilterMessages(response.Messages);

    Console.WriteLine("Guardrail Middleware - Filtered messages Post-Run");

    return response;

    List<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Select(m => new ChatMessage(m.Role, FilterContent(m.Text))).ToList();
    }

    static string FilterContent(string content)
    {
        foreach (var keyword in new[] { "harmful", "illegal", "violence" })
        {
            if (content.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            {
                return "[REDACTED: Forbidden content]";
            }
        }

        return content;
    }
}

// This middleware handles Human in the loop console interaction for any user approval required during function calling.
async Task<AgentRunResponse> ConsolePromptingApprovalMiddleware(IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    AgentRunResponse response = await innerAgent.RunAsync(messages, thread, options, cancellationToken);

    List<UserInputRequestContent> userInputRequests = response.UserInputRequests.ToList();

    while (userInputRequests.Count > 0)
    {
        // Ask the user to approve each function call request.
        // For simplicity, we are assuming here that only function approval requests are being made.

        // Pass the user input responses back to the agent for further processing.
        response.Messages = userInputRequests
            .OfType<FunctionApprovalRequestContent>()
            .Select(functionApprovalRequest =>
            {
                Console.WriteLine($"The agent would like to invoke the following function, please reply Y to approve: Name {functionApprovalRequest.FunctionCall.Name}");
                bool approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
                return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved)]);
            })
            .ToList();

        response = await innerAgent.RunAsync(response.Messages, thread, options, cancellationToken);

        userInputRequests = response.UserInputRequests.ToList();
    }

    return response;
}

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(middlewareEnabledAgent.Name);
