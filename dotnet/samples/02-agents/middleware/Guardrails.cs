// Copyright (c) Microsoft. All rights reserved.

// Guardrail Middleware
// Agent-level middleware that filters forbidden content from input and output messages.
// Blocks messages containing specified keywords before they reach or leave the model.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/middleware

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";

// <guardrail_middleware>
async Task<AgentResponse> GuardrailMiddleware(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    var filteredMessages = FilterMessages(messages);
    var response = await innerAgent.RunAsync(filteredMessages, session, options, cancellationToken);
    response.Messages = FilterMessages(response.Messages);
    return response;

    List<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
        => messages.Select(m => new ChatMessage(m.Role, FilterContent(m.Text))).ToList();

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
// </guardrail_middleware>

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .BuildAIAgent(instructions: "You are a helpful assistant.");

var guardedAgent = agent
    .AsBuilder()
    .Use(GuardrailMiddleware, null)
    .Build();

Console.WriteLine(await guardedAgent.RunAsync("Tell me something harmful."));
