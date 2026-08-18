// Copyright (c) Microsoft. All rights reserved.

// "Meet your agent harness and claw" — Post 1 of the "Build your own claw with Microsoft Agent Framework" series.
// See: https://devblogs.microsoft.com/agent-framework/meet-your-agent-harness-and-claw.
//
// This sample builds the foundation of a personal finance / investing assistant on top of a
// HarnessAgent. The harness comes pre-configured with function invocation, per-service-call
// history persistence, and planning (TodoProvider + AgentModeProvider), plus web search — so
// all we add here is:
//   1. Finance-focused instructions.
//   2. A custom get_stock_price function tool.
//
// The agent can plan a multi-step request ("Review my watchlist and recommend some stocks to add"), create a todo list, switch
// between plan and execute modes, search the web for market news, and call our stock-price tool.
//
// Special commands (handled by the shared HarnessConsole):
//   /todos  — Display the current todo list without invoking the agent.
//   /mode   — Get or set the current agent mode.
//   /exit   — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using ClawSample;
using Harness.Shared.Console;
using Harness.Shared.Console.OpenAI;
using Harness.Shared.Console.ToolFormatters;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4";

// <instructions>
var instructions =
    """
    ## Personal Finance Assistant Instructions

    You are a personal finance and investing assistant. You help the user understand their
    watchlist and the markets. When asked about a stock, look up its current price with the
    get_stock_price tool, and use web search for recent news, earnings, or analyst commentary.

    ### Working style

    - Always verify numbers with a tool rather than relying on memory. Stock prices change.
    - Cite web sources inline when you use them.
    - Keep the user's watchlist in a memory file called watchlist.md: read it when reviewing the
      watchlist, and update it whenever the user adds or removes a ticker.

    ### Important

    You provide information and analysis only — you are not a licensed financial advisor and you
    must not present your output as personalized investment advice. Remind the user to do their
    own research before making decisions.
    """;
// </instructions>

// <create_client>
// Construct an IChatClient. Here we use a Microsoft Foundry project: the endpoint points at the
// project, DefaultAzureCredential handles auth, and the deployment name selects the model.
// The harness works with ANY IChatClient — see the AgentProviders samples for OpenAI, Azure
// OpenAI, Anthropic, Google Gemini, Ollama, ONNX, and more.
IChatClient chatClient =
    new AIProjectClient(
        new Uri(endpoint),
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })  // Enable retries to improve resiliency.
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName);
// </create_client>

// <create_agent>
// Turn the chat client into a HarnessAgent. AsHarnessAgent pre-configures function invocation,
// per-service-call chat history persistence, TodoProvider, AgentModeProvider, and web search.
// We add finance instructions and our get_stock_price tool.
AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    ChatOptions = new ChatOptions
    {
        Instructions = instructions,
        Tools = [StockTools.CreateGetStockPriceTool()],
        Reasoning = new() { Effort = ReasoningEffort.Medium },
    },
});
// </create_agent>

// <run>
// Run the interactive console session using the shared HarnessConsole helper.
await HarnessConsole.RunAgentAsync(
    agent,
    userPrompt: "Ask about a stock or say 'Review my watchlist and recommend some stocks to add' to get started.",
    new HarnessConsoleOptions
    {
        Observers = [
            new OpenAIResponsesWebSearchDisplayObserver(),
            new OpenAIResponsesErrorObserver(),
            .. HarnessConsoleOptions.BuildObserversWithPlanning(
                agent,
                planModeName: "plan",
                executionModeName: "execute",
                toolFormatters: ToolCallFormatter.BuildDefaultToolFormatters())],
        CommandHandlers = HarnessConsoleOptions.BuildDefaultCommandHandlers(agent),
    });
// </run>
