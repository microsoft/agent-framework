// Copyright (c) Microsoft. All rights reserved.

// This sample shows multiple middleware layers working together with a ChatClientAgent:
// agent run (PII filtering and guardrails),
// function invocation (logging and result overrides), and human-in-the-loop
// approval workflows for sensitive function calls.

using System.ComponentModel;
using System.Text.RegularExpressions;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

[Description("The current datetime offset.")]
static string GetDateTime()
    => DateTimeOffset.Now.ToString();

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AITool dateTimeTool = AIFunctionFactory.Create(GetDateTime, name: nameof(GetDateTime));
AITool getWeatherTool = AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather));

AIAgent originalAgent = aiProjectClient.AsAIAgent(deploymentName,
    instructions: "You are an AI assistant that helps people find information.",
    name: "InformationAssistant",
    tools: [getWeatherTool, dateTimeTool]);

// Adding middleware to the agent level
AIAgent middlewareEnabledAgent = originalAgent
    .AsBuilder()
    .Use(FunctionCallMiddleware)
    .Use(FunctionCallOverrideWeather)
    .Use(PIIMiddleware, null)
    .Use(GuardrailMiddleware, null)
    .Build();

AgentSession session = await middlewareEnabledAgent.CreateSessionAsync();

Console.WriteLine("\n\n=== Example 1: Wording Guardrail ===");
AgentResponse guardRailedResponse = await middlewareEnabledAgent.RunAsync("Tell me something harmful.");
Console.WriteLine($"Guard railed response: {guardRailedResponse}");

Console.WriteLine("\n\n=== Example 2: PII detection ===");
AgentResponse piiResponse = await middlewareEnabledAgent.RunAsync("My name is John Doe, call me at 123-456-7890 or email me at john@something.com");
Console.WriteLine($"Pii filtered response: {piiResponse}");

Console.WriteLine("\n\n=== Example 3: Agent function middleware ===");
AgentResponse functionCallResponse = await middlewareEnabledAgent.RunAsync("What's the current time and the weather in Seattle?", session);
Console.WriteLine($"Function calling response: {functionCallResponse}");

// Special per-request middleware agent.
Console.WriteLine("\n\n=== Example 4: Middleware with human in the loop function approval ===");

AIAgent humanInTheLoopAgent = aiProjectClient.AsAIAgent(deploymentName,
    instructions: "You are a Human in the loop testing AI assistant that helps people find information.",
    name: "HumanInTheLoopAgent",
    tools: [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather)))]);

AgentResponse response = await humanInTheLoopAgent
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
        result = "The weather is sunny with a high of 25°C.";
    }
    Console.WriteLine($"Function Name: {context!.Function.Name} - Middleware 2 Post-Invoke");
    return result;
}

// This middleware redacts PII information from input and output messages.
async Task<AgentResponse> PIIMiddleware(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    var filteredMessages = FilterMessages(messages);
    Console.WriteLine("Pii Middleware - Filtered Messages Pre-Run");

    var agentResponse = await innerAgent.RunAsync(filteredMessages, session, options, cancellationToken).ConfigureAwait(false);

    agentResponse.Messages = FilterMessages(agentResponse.Messages);

    Console.WriteLine("Pii Middleware - Filtered Messages Post-Run");

    return agentResponse;

    static IList<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
    }

    static string FilterPii(string content)
    {
        Regex[] piiPatterns = [
            MyRegex(),
            EmailRegex(),
            FullNameRegex()
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
    var filteredMessages = FilterMessages(messages);

    Console.WriteLine("Guardrail Middleware - Filtered messages Pre-Run");

    var agentResponse = await innerAgent.RunAsync(filteredMessages, session, options, cancellationToken);

    agentResponse.Messages = FilterMessages(agentResponse.Messages);

    Console.WriteLine("Guardrail Middleware - Filtered messages Post-Run");

    return agentResponse;

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
    AgentResponse agentResponse = await innerAgent.RunAsync(messages, session, options, cancellationToken);

    List<ToolApprovalRequestContent> approvalRequests = agentResponse.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();

    while (approvalRequests.Count > 0)
    {
        agentResponse.Messages = approvalRequests
            .ConvertAll(functionApprovalRequest =>
            {
                Console.WriteLine($"The agent would like to invoke the following function, please reply Y to approve: Name {((FunctionCallContent)functionApprovalRequest.ToolCall).Name}");
                bool approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
                return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved)]);
            });

        agentResponse = await innerAgent.RunAsync(agentResponse.Messages, session, options, cancellationToken);

        approvalRequests = agentResponse.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
    }

    return agentResponse;
}

internal partial class Program
{
    [GeneratedRegex(@"\b\d{3}-\d{3}-\d{4}\b", RegexOptions.Compiled)]
    private static partial Regex MyRegex();

    [GeneratedRegex(@"\b[\w\.-]+@[\w\.-]+\.\w+\b", RegexOptions.Compiled)]
    private static partial Regex EmailRegex();

    [GeneratedRegex(@"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", RegexOptions.Compiled)]
    private static partial Regex FullNameRegex();
}
