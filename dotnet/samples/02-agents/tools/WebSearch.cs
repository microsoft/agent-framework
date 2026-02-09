// Copyright (c) Microsoft. All rights reserved.

// Web Search Tool
// Use a hosted web search tool so the agent can search the internet.
// Note: Web search is available via OpenAI Responses API.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/tools

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// <web_search>
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetResponsesClient(deploymentName)
    .AsAIAgent(
        instructions: "You are a helpful assistant that can search the web for current information.",
        name: "WebSearchAgent",
        tools: [new HostedWebSearchTool()]);

AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("What are the latest developments in AI agents?", session));
// </web_search>
