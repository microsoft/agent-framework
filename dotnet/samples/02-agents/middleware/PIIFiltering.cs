// Copyright (c) Microsoft. All rights reserved.

// PII Filtering Middleware
// Agent-level middleware that detects and redacts PII (personally identifiable information)
// from both input and output messages using regex patterns.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/middleware

using System.Text.RegularExpressions;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";

// <pii_middleware>
async Task<AgentResponse> PIIMiddleware(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    var filteredMessages = FilterMessages(messages);
    var response = await innerAgent.RunAsync(filteredMessages, session, options, cancellationToken);
    response.Messages = FilterMessages(response.Messages);
    return response;

    static IList<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
        => messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();

    static string FilterPii(string content)
    {
        Regex[] piiPatterns =
        [
            new(@"\b\d{3}-\d{3}-\d{4}\b", RegexOptions.Compiled),   // Phone numbers
            new(@"\b[\w\.-]+@[\w\.-]+\.\w+\b", RegexOptions.Compiled), // Email addresses
            new(@"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", RegexOptions.Compiled) // Full names
        ];

        foreach (var pattern in piiPatterns)
        {
            content = pattern.Replace(content, "[REDACTED: PII]");
        }
        return content;
    }
}
// </pii_middleware>

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .BuildAIAgent(instructions: "You are a helpful assistant.");

var piiAgent = agent
    .AsBuilder()
    .Use(PIIMiddleware, null)
    .Build();

Console.WriteLine(await piiAgent.RunAsync("My name is John Doe, call me at 123-456-7890 or email me at john@something.com"));
