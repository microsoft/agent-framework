// Copyright (c) Microsoft. All rights reserved.

// This sample shows multiple middleware layers working together with Azure OpenAI:
// chat client (global/per-request), agent run (PII filtering and guardrails),
// function invocation (logging and result overrides), human-in-the-loop
// approval workflows for sensitive function calls, and MessageAIContextProvider
// middleware for injecting additional context messages into the agent pipeline.

using System.ComponentModel;
using System.Text.RegularExpressions;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

// Get Azure AI Foundry configuration from environment variables
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = System.Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";

// Get a client to create/retrieve server side agents with
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var azureOpenAIClient = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deploymentName);

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

[Description("The current datetime offset.")]
static string GetDateTime()
    => DateTimeOffset.Now.ToString();

// Adding middleware to the chat client level and building an agent on top of it
var originalAgent = azureOpenAIClient.AsIChatClient()
    .AsBuilder()
    .Use(getResponseFunc: ChatClientMiddleware, getStreamingResponseFunc: null)
    .BuildAIAgent(
        instructions: "You are an AI assistant that helps people find information.",
        tools: [AIFunctionFactory.Create(GetDateTime, name: nameof(GetDateTime))]);

// Adding middleware to the agent level
var middlewareEnabledAgent = originalAgent
    .AsBuilder()
    .Use(FunctionCallMiddleware)
    .Use(FunctionCallOverrideWeather)
    .Use(PIIMiddleware, null)
    .Use(GuardrailMiddleware, null)
    .Build();

var session = await middlewareEnabledAgent.CreateSessionAsync();

Console.WriteLine("\n\n=== Example 1: Wording Guardrail ===");
var guardRailedResponse = await middlewareEnabledAgent.RunAsync("Tell me something harmful.");
Console.WriteLine($"Guard railed response: {guardRailedResponse}");

Console.WriteLine("\n\n=== Example 2: PII detection ===");
var piiResponse = await middlewareEnabledAgent.RunAsync("My name is John Doe, call me at 123-456-7890 or email me at john@something.com");
Console.WriteLine($"Pii filtered response: {piiResponse}");

Console.WriteLine("\n\n=== Example 3: Agent function middleware ===");

// Agent function middleware support is limited to agents that wraps a upstream ChatClientAgent or derived from it.

// Add Per-request tools
var options = new ChatClientAgentRunOptions(new()
{
    Tools = [AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather))]
});

var functionCallResponse = await middlewareEnabledAgent.RunAsync("What's the current time and the weather in Seattle?", session, options);
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
        .Use(PerRequestChatClientMiddleware, null) // Using the non-streaming for handling streaming as well
        .Build()
};

// var response = middlewareAgent  // Using per-request middleware pipeline in addition to existing agent-level middleware
var response = await originalAgent // Using per-request middleware pipeline without existing agent-level middleware
    .AsBuilder()
    .Use(PerRequestFunctionCallingMiddleware)
    .Use(ConsolePromptingApprovalMiddleware, null)
    .Build()
    .RunAsync("What's the current time and the weather in Seattle?", session, optionsWithApproval);

Console.WriteLine($"Per-request middleware response: {response}");

// MessageAIContextProvider middleware that injects additional messages into the agent request.
// This allows any AIAgent (not just ChatClientAgent) to benefit from MessageAIContextProvider-based
// context enrichment. Multiple providers can be passed to Use and they are called in sequence,
// each receiving the output of the previous one.
Console.WriteLine("\n\n=== Example 5: MessageAIContextProvider middleware ===");

var contextProviderAgent = originalAgent
    .AsBuilder()
    .UseAIContextProviders(new DateTimeContextProvider())
    .Build();

var contextResponse = await contextProviderAgent.RunAsync("Is it almost time for lunch?");
Console.WriteLine($"Context-enriched response: {contextResponse}");

// AIContextProvider at the chat client level. Unlike the agent-level MessageAIContextProvider,
// this operates within the IChatClient pipeline and can also enrich tools and instructions.
// It must be used within the context of a running AIAgent (uses AIAgent.CurrentRunContext).
// In this case we are attaching an AIContextProvider that only adds messages.
Console.WriteLine("\n\n=== Example 6: AIContextProvider on chat client pipeline ===");

var chatClientProviderAgent = azureOpenAIClient.AsIChatClient()
    .AsBuilder()
    .UseAIContextProviders(new DateTimeContextProvider())
    .BuildAIAgent(
        instructions: "You are an AI assistant that helps people find information.");

var chatClientContextResponse = await chatClientProviderAgent.RunAsync("Is it almost time for lunch?");
Console.WriteLine($"Chat client context-enriched response: {chatClientContextResponse}");

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

// There's no difference per-request middleware, except it's added to the agent and used for a single agent run.
// This middleware logs function names before and after they are invoked.
async ValueTask<object?> PerRequestFunctionCallingMiddleware(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
{
    Console.WriteLine($"Agent Id: {agent.Id}");
    Console.WriteLine($"Function Name: {context!.Function.Name} - Per-Request Pre-Invoke");
    var result = await next(context, cancellationToken);
    Console.WriteLine($"Function Name: {context!.Function.Name} - Per-Request Post-Invoke");
    return result;
}

// This middleware redacts PII information from input and output messages.
async Task<AgentResponse> PIIMiddleware(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    // Redact PII information from input messages
    var filteredMessages = FilterMessages(messages);
    Console.WriteLine("Pii Middleware - Filtered Messages Pre-Run");

    var response = await innerAgent.RunAsync(filteredMessages, session, options, cancellationToken).ConfigureAwait(false);

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
        Regex[] piiPatterns =
        [
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
async Task<AgentResponse> GuardrailMiddleware(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    // Redact keywords from input messages
    var filteredMessages = FilterMessages(messages);

    Console.WriteLine("Guardrail Middleware - Filtered messages Pre-Run");

    // Proceed with the agent run
    var response = await innerAgent.RunAsync(filteredMessages, session, options, cancellationToken);

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
async Task<AgentResponse> ConsolePromptingApprovalMiddleware(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    AgentResponse response = await innerAgent.RunAsync(messages, session, options, cancellationToken);

    // For simplicity, we are assuming here that only function approvals are pending.
    List<FunctionApprovalRequestContent> approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();

    while (approvalRequests.Count > 0)
    {
        // Ask the user to approve each function call request.
        // Pass the user input responses back to the agent for further processing.
        response.Messages = approvalRequests
            .ConvertAll(functionApprovalRequest =>
            {
                Console.WriteLine($"The agent would like to invoke the following function, please reply Y to approve: Name {functionApprovalRequest.FunctionCall.Name}");
                return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false)]);
            });

        response = await innerAgent.RunAsync(response.Messages, session, options, cancellationToken);

        approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();
    }

    return response;
}

// This middleware handles chat client lower level invocations.
// This is useful for handling agent messages before they are sent to the LLM and also handle any response messages from the LLM before they are sent back to the agent.
async Task<ChatResponse> ChatClientMiddleware(IEnumerable<ChatMessage> message, ChatOptions? options, IChatClient innerChatClient, CancellationToken cancellationToken)
{
    Console.WriteLine("Chat Client Middleware - Pre-Chat");
    var response = await innerChatClient.GetResponseAsync(message, options, cancellationToken);
    Console.WriteLine("Chat Client Middleware - Post-Chat");

    return response;
}

// There's no difference per-request middleware, except it's added to the chat client and used for a single agent run.
// This middleware handles chat client lower level invocations.
// This is useful for handling agent messages before they are sent to the LLM and also handle any response messages from the LLM before they are sent back to the agent.
async Task<ChatResponse> PerRequestChatClientMiddleware(IEnumerable<ChatMessage> message, ChatOptions? options, IChatClient innerChatClient, CancellationToken cancellationToken)
{
    Console.WriteLine("Per-Request Chat Client Middleware - Pre-Chat");
    var response = await innerChatClient.GetResponseAsync(message, options, cancellationToken);
    Console.WriteLine("Per-Request Chat Client Middleware - Post-Chat");

    return response;
}

/// <summary>
/// A <see cref="MessageAIContextProvider"/> that injects the current date and time into the agent's context.
/// This is a simple example of how to use a MessageAIContextProvider to enrich agent messages
/// via the <see cref="AIAgentBuilder.UseAIContextProviders(MessageAIContextProvider[])"/> extension method.
/// </summary>
internal sealed class DateTimeContextProvider : MessageAIContextProvider
{
    protected override ValueTask<IEnumerable<ChatMessage>> ProvideMessagesAsync(
        InvokingContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine("DateTimeContextProvider - Injecting current date/time context");

        return new ValueTask<IEnumerable<ChatMessage>>(
            [
                new ChatMessage(ChatRole.User, $"For reference, the current date and time is: {DateTimeOffset.Now}")
            ]);
    }
}
