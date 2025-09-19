// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

// Get Azure AI Foundry configuration from environment variables
var endpoint = Environment.GetEnvironmentVariable("AZUREOPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var persistentEndpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = System.Environment.GetEnvironmentVariable("AZUREOPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";

// Get a client to create/retrieve server side agents with
var azureOpenAIClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName);

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

[Description("The current datetime offset.")]
static string GetDateTime()
    => DateTimeOffset.Now.ToString();

// Adding middleware to the chat client level
var chatClient = azureOpenAIClient.AsIChatClient()
    .AsBuilder()
        .Use(ChatClientMiddleware)
    .Build();

// For flexibility we create the agent without any middleware.
var originalAgent = new ChatClientAgent(chatClient, new ChatClientAgentOptions(
        instructions: "You are an AI assistant that helps people find information.",
        // Agent level tools
        tools: [AIFunctionFactory.Create(GetDateTime, name: nameof(GetDateTime))]));

// Adding middleware to the agent level
var middlewareEnabledAgent = originalAgent
    .AsBuilder()
        .Use(FunctionCallMiddleware1)
        .Use(FunctionCallOverrideWeather)
        .Use(PIIMiddleware)
        .Use(GuardrailMiddleware)
    .Build();

var thread = middlewareEnabledAgent.GetNewThread();

Console.WriteLine("\n\n=== Example 1: Wording Guardrail ===");
var guardRailedResponse = await middlewareEnabledAgent.RunAsync("Tell me something harmful.");
Console.WriteLine($"Guard railed response: {guardRailedResponse}");

Console.WriteLine("\n\n=== Example 2: PII detection ===");
var piiResponse = await middlewareEnabledAgent.RunAsync("My name is John Doe, call me at 123-456-7890 or email me at john@something.com");
Console.WriteLine($"Pii filtered response: {piiResponse}");

Console.WriteLine("\n\n=== Example 3: Agent function middleware ===");

// Add Per-request tools
var options = new ChatClientAgentRunOptions(new()
{
    Tools = [AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather))]
});

var functionCallResponse = await middlewareEnabledAgent.RunAsync("What's the current time and the weather in Seattle?", thread, options);
Console.WriteLine($"Function calling response: {functionCallResponse}");

// Special per-request middleware agent.
Console.WriteLine("\n\n=== Example 4: Per-request middleware with human in the loop function approval ===");

var optionsWithApproval = new ChatClientAgentRunOptions(new()
{
    // Adding a function with approval required
    Tools = [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather)))],
})
{
    ChatClientFactory = (chatClient) => chatClient
        .AsBuilder()
            .Use(PerRequestChatClientMiddleware)
        .Build()
};

// var response = middlewareAgent  // Using per-request middleware in addition to agent-level middleware
var response = await originalAgent // Using per-request middleware without agent-level middleware
    .AsBuilder()
        .Use(PerRequestFunctionCallingMiddleware)
        .Use(ConsolePromptingApprovalMiddleware)
    .Build()
    .RunAsync("What's the current time and the weather in Seattle?", thread, optionsWithApproval);

Console.WriteLine($"Per-request middleware response: {response}");

async Task FunctionCallMiddleware1(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
{
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 1 Pre-Invoke");
    await next(context);
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 1 Post-Invoke");
}

async Task FunctionCallOverrideWeather(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
{
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 2 Pre-Invoke");
    await next(context);

    if (context.Function.Name == nameof(GetWeather))
    {
        // Override the result of the GetWeather function
        context.FunctionResult = "The weather is sunny with a high of 25°C.";
    }
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 2 Post-Invoke");
}

async Task PerRequestFunctionCallingMiddleware(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
{
    Console.WriteLine($"Function Name: {context!.Function.Name} - Per-Request Pre-Invoke");
    await next(context);
    Console.WriteLine($"Function Name: {context!.Function.Name} - Per-Request Post-Invoke");
}

async Task PIIMiddleware(AgentRunContext context, Func<AgentRunContext, Task> next)
{
    // Guardrail: Filter input messages for PII
    context.Messages = FilterMessages(context.Messages);
    Console.WriteLine("Pii Middleware - Filtered Messages Pre-Run");

    await next(context).ConfigureAwait(false);

    // Guardrail: Filter output messages for PII
    context.RunResponse!.Messages = FilterMessages(context.RunResponse!.Messages);

    Console.WriteLine("Pii Middleware - Filtered Messages Post-Run");

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

async Task GuardrailMiddleware(AgentRunContext context, Func<AgentRunContext, Task> next)
{
    // Guardrail: Simple keyword-based filtering

    context.Messages = FilterMessages(context.Messages);

    Console.WriteLine("Guardrail Middleware - Filtered messages Pre-Run");

    // Proceed with the agent run
    await next(context);

    context.RunResponse!.Messages = FilterMessages(context.RunResponse!.Messages);

    Console.WriteLine("Guardrail Middleware - Filtered messages Post-Run");

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

async Task ConsolePromptingApprovalMiddleware(AgentRunContext context, Func<AgentRunContext, Task> next)
{
    await next(context);

    var userInputRequests = context.RunResponse!.UserInputRequests.ToList();

    while (userInputRequests.Count > 0)
    {
        // Ask the user to approve each function call request.
        // For simplicity, we are assuming here that only function approval requests are being made.

        // Pass the user input responses back to the agent for further processing.
        context.Messages = userInputRequests
            .OfType<FunctionApprovalRequestContent>()
            .Select(functionApprovalRequest =>
            {
                Console.WriteLine($"The agent would like to invoke the following function, please reply Y to approve: Name {functionApprovalRequest.FunctionCall.Name}");
                return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false)]);
            })
            .ToList();

        await next(context);

        userInputRequests = context.RunResponse!.UserInputRequests.ToList();
    }
}

async Task ChatClientMiddleware(IEnumerable<ChatMessage> message, ChatOptions? options, Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, Task> next, CancellationToken cancellationToken)
{
    Console.WriteLine("Chat Client Middleware - Pre-Chat");
    await next(message, options, cancellationToken);
    Console.WriteLine("Chat Client Middleware - Post-Chat");
}

async Task PerRequestChatClientMiddleware(IEnumerable<ChatMessage> message, ChatOptions? options, Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, Task> next, CancellationToken cancellationToken)
{
    Console.WriteLine("Per-Request Chat Client Middleware - Pre-Chat");
    await next(message, options, cancellationToken);
    Console.WriteLine("Per-Request Chat Client Middleware - Post-Chat");
}
