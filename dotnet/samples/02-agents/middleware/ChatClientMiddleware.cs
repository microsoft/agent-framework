// Copyright (c) Microsoft. All rights reserved.

// Chat Client Middleware
// Add middleware at the chat client level to intercept LLM requests and responses.
// Useful for logging, modifying prompts, or transforming responses before they reach the agent.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/middleware

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";

[Description("The current datetime offset.")]
static string GetDateTime() => DateTimeOffset.Now.ToString();

// <chat_client_middleware>
async Task<ChatResponse> ChatClientMiddleware(IEnumerable<ChatMessage> messages, ChatOptions? options, IChatClient innerChatClient, CancellationToken cancellationToken)
{
    Console.WriteLine("[ChatClient Middleware] Pre-Chat");
    var response = await innerChatClient.GetResponseAsync(messages, options, cancellationToken);
    Console.WriteLine("[ChatClient Middleware] Post-Chat");
    return response;
}

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .AsBuilder()
    .Use(getResponseFunc: ChatClientMiddleware, getStreamingResponseFunc: null)
    .BuildAIAgent(
        instructions: "You are an AI assistant.",
        tools: [AIFunctionFactory.Create(GetDateTime, name: nameof(GetDateTime))]);
// </chat_client_middleware>

Console.WriteLine(await agent.RunAsync("What time is it?"));
