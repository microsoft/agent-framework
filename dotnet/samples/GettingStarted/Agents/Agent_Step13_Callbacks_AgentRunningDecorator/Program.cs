// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1110 // Declare type inside namespace
#pragma warning disable CA1812 // Declare type inside namespace

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;

// Create a logger factory for the sample
using var loggerFactory = LoggerFactory.Create(builder =>
    builder.AddConsole().SetMinimumLevel(LogLevel.Information));

// Get Azure AI Foundry configuration from environment variables
var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = System.Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4o-mini";

// Get a client to create/retrieve server side agents with
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Example 3: Agent with custom middleware
Console.WriteLine("=== Agent with custom middleware ===");

var agent = persistentAgentsClient.CreateAIAgent(model, middlewareConfig =>
    middlewareConfig
        .AddRunningMiddleware(PiiRunningMiddleware)
        .AddRunningMiddleware(GuardrailRunningMiddleware)
);

Console.WriteLine("=== Wording Guardrail ===");
var guardRailedResponse = await agent.RunAsync("Tell me something harmful.");
Console.WriteLine(guardRailedResponse);

Console.WriteLine("=== PII detection ===");
var piiResponse = await agent.RunAsync("My name is John Doe, call me at 123-456-7890 or email me at john@something.com");
Console.WriteLine(piiResponse);

// Cleanup
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
async Task PiiRunningMiddleware(AgentRunContext context, Func<AgentRunContext, Task> next)
{
    // Guardrail: Filter input messages for PII
    context.Messages = FilterMessages(context.Messages);
    Console.WriteLine($"Pii Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");

    await next(context).ConfigureAwait(false);

    // Guardrail: Filter output messages for PII
    context.RunResponse!.Messages = FilterMessages(context.RunResponse!.Messages);

    static IList<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();

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
}

async Task GuardrailRunningMiddleware(AgentRunContext context, Func<AgentRunContext, Task> next)
{
    // Guardrail: Simple keyword-based filtering
    var forbiddenKeywords = new[] { "harmful", "illegal", "violence" }; // Expand as needed

    context.Messages = FilterMessages(context.Messages);

    Console.WriteLine($"Guardrail Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");

    await next(context);

    context.RunResponse!.Messages = FilterMessages(context.RunResponse!.Messages);

    List<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Select(m => new ChatMessage(m.Role, FilterContent(m.Text))).ToList();
    }

    string FilterContent(string content)
    {
        foreach (var keyword in forbiddenKeywords)
        {
            if (content.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            {
                return "[REDACTED: Forbidden content]";
            }
        }
        return content;
    }
}
