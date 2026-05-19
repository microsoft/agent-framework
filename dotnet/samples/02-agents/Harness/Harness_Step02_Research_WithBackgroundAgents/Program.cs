// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the BackgroundAgentsProvider to delegate work to background agents.
// A parent agent is given a list of stock tickers and instructed to find the closing price
// for each ticker on December 31, 2025. It delegates the web searches to a background agent.
// The HarnessAgent provides built-in WebSearch (HostedWebSearchTool) so no manual web search
// tool configuration is needed on the background agent.
//
// Special commands:
//   /exit    — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using Harness.Shared.Console;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;
const string TracingSourceName = "Harness.SubAgents";

// Set up OpenTelemetry tracing that writes spans to a text file.
using var tracerProvider = HarnessTracing.CreateFileTracerProvider(TracingSourceName);

// Create the AIProjectClient for communicating with the Foundry responses service.
var projectClient = new AIProjectClient(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) });

// --- Background agent: Web Search Agent ---
// This agent uses the HarnessAgent's built-in HostedWebSearchTool to search the web.
// Features not needed by this sub-agent are disabled.
AIAgent webSearchAgent =
    projectClient
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "WebSearchAgent",
        Description = "An agent that can search the web to find information.",
        OpenTelemetrySourceName = TracingSourceName,
        DisableTodoProvider = true,
        DisableAgentModeProvider = true,
        DisableFileMemory = true,   // If enabled, this would allow the agent to store memories as files in a directory associated with the current session
        DisableFileAccess = true,   // If enabled, this would allow the agent to read/write files in a working directory
        DisableToolApproval = true, // If enabled, this allows don't-ask-again approval functionality.
        ChatOptions = new ChatOptions
        {
            Instructions = "You are a web search assistant. When asked to find information, use the web search tool to look it up and return a concise, factual answer.",
        },
    });

// --- Parent agent: Stock Price Researcher ---
// This agent orchestrates the background agent to look up stock prices in parallel.
var parentInstructions =
    """
    You are a stock price research assistant. You have access to a web search background agent that can look up information on the web.

    When given a list of stock tickers, your job is to find the closing price for each ticker on December 31, 2025.

    ## Workflow

    1. For each ticker, start a background task on the WebSearchAgent asking it to find the closing price on December 31, 2025.
       - Start all background tasks before waiting for any of them to complete, so they run concurrently.
    2. Wait for all background tasks to complete.
    3. Retrieve the results from each background task.
    4. Present a summary table with the ticker symbol and closing price for each stock.
    5. Clear all completed tasks to free memory.

    ## Important

    - Always delegate web searches to the WebSearchAgent background agent. Do not try to answer from memory.
    - If a background task fails or returns unclear results, continue the task with a more specific query.
    - Present results in a clean markdown table format.
    """;

// --- Parent agent: Stock Price Researcher ---
// This agent orchestrates the sub-agent to look up stock prices in parallel.
// Most features are disabled since the parent only needs SubAgentsProvider.
AIAgent parentAgent =
    projectClient
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "StockPriceResearcher",
        Description = "An agent that researches stock prices using background agents.",
        OpenTelemetrySourceName = TracingSourceName,
        DisableTodoProvider = true,
        DisableAgentModeProvider = true,
        DisableFileMemory = true,   // If enabled, this would allow the agent to store memories as files in a directory associated with the current session
        DisableFileAccess = true,   // If enabled, this would allow the agent to read/write files in a working directory
        DisableToolApproval = true, // If enabled, this allows don't-ask-again approval functionality.
        DisableWebSearch = true,
        AIContextProviders =
        [
            new BackgroundAgentsProvider([webSearchAgent]),
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
    userPrompt: "Enter a list of stock tickers (e.g., BAC, MSFT, BA):");
