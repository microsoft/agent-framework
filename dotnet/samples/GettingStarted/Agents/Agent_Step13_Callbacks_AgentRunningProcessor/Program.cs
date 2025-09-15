// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1110 // Declare type inside namespace
#pragma warning disable CA1812 // Declare type inside namespace

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
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

var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .UseCallbacks(config =>
    {
        config.AddCallback(new PiiDetectionMiddleware());
        config.AddCallback(new GuardrailCallbackMiddleware());
    }).Build();

Console.WriteLine("=== Wording Guardrail ===");
var guardRailedResponse = await agent.RunAsync("Tell me something harmful.");
Console.WriteLine(guardRailedResponse);

Console.WriteLine("=== Wording Guardrail - Streaming ===");
await foreach (var update in agent.RunStreamingAsync("Tell me something illegal."))
{
    Console.WriteLine(update);
}

Console.WriteLine("=== PII detection ===");
var piiResponse = await agent.RunAsync("My name is John Doe, call me at 123-456-7890 or email me at john@something.com");
Console.WriteLine(piiResponse);

Console.WriteLine("=== PII detection - Streaming ===");
await foreach (var update in agent.RunStreamingAsync("My name is Jane Smith, call me at 987-654-3210."))
{
    Console.WriteLine(update);
}

// Cleanup
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);

internal sealed class PiiDetectionMiddleware : CallbackMiddleware<AgentInvokeCallbackContext>
{
    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        // Guardrail: Filter input messages for PII
        context.Messages = context.Messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
        Console.WriteLine($"Pii Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");
        await next(context).ConfigureAwait(false);

        if (!context.IsStreaming)
        {
            // Guardrail: Filter output messages for PII
            context.Messages = context.Messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
        }
        else
        {
            context.SetRawResponse(StreamingPiiDetectionAsync(context.RunStreamingResponse!));
        }

        async IAsyncEnumerable<AgentRunResponseUpdate> StreamingPiiDetectionAsync(IAsyncEnumerable<AgentRunResponseUpdate> upstream)
        {
            await foreach (var update in upstream)
            {
                if (update.Text != null)
                {
                    yield return new AgentRunResponseUpdate(update.Role, FilterPii(update.Text));
                }
                else
                {
                    yield return update;
                }
            }
        }
    }

    private static string FilterPii(string content)
    {
        // Regex patterns for PII detection (simplified for demonstration)
        var piiPatterns = new[]
        {
                new Regex(@"\b\d{3}-\d{3}-\d{4}\b", RegexOptions.Compiled), // Phone number (e.g., 123-456-7890)
                new Regex(@"\b[\w\.-]+@[\w\.-]+\.\w+\b", RegexOptions.Compiled), // Email address
                new Regex(@"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", RegexOptions.Compiled) // Full name (e.g., John Doe)
            };

        foreach (var pattern in piiPatterns)
        {
            content = pattern.Replace(content, "[REDACTED: PII]");
        }
        return content;
    }
}

internal sealed class GuardrailCallbackMiddleware : CallbackMiddleware<AgentInvokeCallbackContext>
{
    private readonly string[] _forbiddenKeywords = { "harmful", "illegal", "violence" }; // Expand as needed

    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        // Guardrail: Filter input messages for forbidden content
        context.Messages = this.FilterMessages(context.Messages);
        Console.WriteLine($"Guardrail Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");

        await next(context).ConfigureAwait(false);
        if (!context.IsStreaming)
        {
            // Guardrail: Filter output messages for forbidden content
            context.Messages = this.FilterMessages(context.Messages);
        }
        else
        {
            context.SetRawResponse(StreamingGuardRailAsync(context.RunStreamingResponse!));
        }

        async IAsyncEnumerable<AgentRunResponseUpdate> StreamingGuardRailAsync(IAsyncEnumerable<AgentRunResponseUpdate> upstream)
        {
            await foreach (var update in upstream)
            {
                if (update.Text != null)
                {
                    yield return new AgentRunResponseUpdate(update.Role, this.FilterContent(update.Text));
                }
                else
                {
                    yield return update;
                }
            }
        }
    }

    private List<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Select(m => new ChatMessage(m.Role, this.FilterContent(m.Text))).ToList();
    }

    private string FilterContent(string content)
    {
        foreach (var keyword in this._forbiddenKeywords)
        {
            if (content.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            {
                return "[REDACTED: Forbidden content]";
            }
        }
        return content;
    }
}
