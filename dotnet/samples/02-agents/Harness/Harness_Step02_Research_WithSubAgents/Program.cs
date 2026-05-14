// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the SubAgentsProvider to delegate work to sub-agents.
// A parent agent is given a list of stock tickers and instructed to find the closing price
// for each ticker on December 31, 2025. It delegates the web searches to a sub-agent
// equipped with Foundry's hosted web search tool.
//
// Special commands:
//   exit    — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.Identity;
using Harness.Shared.Console;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;

// --- Sub-agent: Web Search Agent ---
// This agent can search the web and is used by the parent agent to look up stock prices.
AIAgent webSearchAgent =
    new OpenAIClient(
        new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions()
        {
            Endpoint = new Uri(endpoint),
            RetryPolicy = new ClientRetryPolicy(3)
        })
    .GetResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "WebSearchAgent",
        Description = "An agent that can search the web to find information.",
        ChatOptions = new ChatOptions
        {
            Instructions = "You are a web search assistant. When asked to find information, use the web search tool to look it up and return a concise, factual answer.",
            Tools =
            [
                ResponseTool.CreateWebSearchTool().AsAITool(),
            ],
        },
    });

// --- Parent agent: Stock Price Researcher ---
// This agent orchestrates the sub-agent to look up stock prices in parallel.
var parentInstructions =
    """
    You are a stock price research assistant. You have access to a web search sub-agent that can look up information on the web.

    When given a list of stock tickers, your job is to find the closing price for each ticker on December 31, 2025.

    ## Workflow

    1. For each ticker, start a sub-task on the WebSearchAgent asking it to find the closing price on December 31, 2025.
       - Start all sub-tasks before waiting for any of them to complete, so they run concurrently.
    2. Wait for all sub-tasks to complete.
    3. Retrieve the results from each sub-task.
    4. Present a summary table with the ticker symbol and closing price for each stock.
    5. Clear all completed tasks to free memory.

    ## Important

    - Always delegate web searches to the WebSearchAgent sub-agent. Do not try to answer from memory.
    - If a sub-task fails or returns unclear results, continue the task with a more specific query.
    - Present results in a clean markdown table format.
    """;

AIAgent parentAgent =
    new OpenAIClient(
        new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions()
        {
            Endpoint = new Uri(endpoint),
            RetryPolicy = new ClientRetryPolicy(3)
        })
    .GetResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "StockPriceResearcher",
        Description = "An agent that researches stock prices using sub-agents.",
        AIContextProviders =
        [
            new SubAgentsProvider([webSearchAgent]),
        ],
        ChatOptions = new ChatOptions
        {
            Instructions = parentInstructions,
            MaxOutputTokens = 16_000,
        },
    });

// Run the interactive console session.
await HarnessConsole.RunAgentAsync(
    parentAgent,
    title: "Stock Price Researcher (SubAgents Demo)",
    userPrompt: "Enter a list of stock tickers (e.g., BAC, MSFT, BA):");
