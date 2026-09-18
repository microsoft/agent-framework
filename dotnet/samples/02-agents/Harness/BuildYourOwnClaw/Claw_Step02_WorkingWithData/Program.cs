// Copyright (c) Microsoft. All rights reserved.

// "Working with your data, safely" — Post 2 of the "Build your own claw and agent harness with Microsoft Agent Framework" series.
// See: https://devblogs.microsoft.com/agent-framework/agent-harness-working-with-your-data-safely.
//
// This sample builds on Post 1's personal finance assistant and adds three abilities:
//   1. File access  — read the user's portfolio.csv and write report files (file_access_* tools).
//   2. Approvals    — the place_trade tool is wrapped so it requires human approval before running.
//   3. Durable memory — two complementary kinds:
//        * File memory   (coarse-grained, explicit) — the agent reads/writes files like
//                         watchlist.md. Its files live on disk under {cwd}/agent-file-memory/<session-id>/,
//                         so they persist across runs on this machine; /session-export and /session-import
//                         preserve the session id so a relaunched session re-links to its memory files.
//        * Foundry memory (fine-grained, automatic) — Microsoft Foundry extracts durable facts
//                         (e.g. the user's risk tolerance) from the conversation. Opt-in: enabled
//                         only when FOUNDRY_MEMORY_STORE and FOUNDRY_EMBEDDING_MODEL are set.
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
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4";

// <instructions>
var instructions =
    """
    ## Personal Finance Assistant Instructions

    You are a personal finance and investing assistant. You help the user understand their
    portfolio and watchlist, and you can place trades on their behalf.

    ### Working style

    - The user's holdings live in a file called portfolio.csv. Read it with the file_access tools
      before answering questions about their portfolio, and never modify it unless asked.
    - When asked for a report or analysis, write it to a Markdown file with the file_access tools
      (e.g. reports/portfolio-review.md) and tell the user where you saved it.
    - Keep the user's watchlist in a memory file called watchlist.md: read it when reviewing the
      watchlist, and update it whenever the user adds or removes a ticker.
    - To buy or sell, use the place_trade tool. This takes a real action, so the user will be
      asked to approve it before it runs — explain what you are about to do first.
    - Remember durable facts the user tells you about themselves (risk tolerance, goals,
      preferences) and take them into account when giving analysis.

    ### Important

    You provide information and analysis only — you are not a licensed financial advisor and you
    must not present your output as personalized investment advice. Remind the user to do their
    own research before making decisions.
    """;
// </instructions>

// <create_client>
// Construct an IChatClient backed by a Microsoft Foundry project (see Post 1 for details).
var projectClient = new AIProjectClient(
    new Uri(endpoint),
    // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
    // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
    // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
    new DefaultAzureCredential(),
    new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) });

IChatClient chatClient = projectClient
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName);
// </create_client>

// <memory>
// Fine-grained Foundry memory is opt-in: it needs a memory store and an embedding model. When the
// environment is configured we add a FoundryMemoryProvider scoped to a single user, so the facts it
// extracts are recalled across sessions. Otherwise we fall back to file memory only.
var memoryStoreName = Environment.GetEnvironmentVariable("FOUNDRY_MEMORY_STORE");
var embeddingModel = Environment.GetEnvironmentVariable("FOUNDRY_EMBEDDING_MODEL");

FoundryMemoryProvider? foundryMemory = null;
if (!string.IsNullOrWhiteSpace(memoryStoreName) && !string.IsNullOrWhiteSpace(embeddingModel))
{
    foundryMemory = new FoundryMemoryProvider(
        projectClient,
        memoryStoreName,
        // In a real world scenario, "claw-sample-user" should be replaced with a unique identifier
        // for the active user.
        // To tie memories to the session, replace "claw-sample-user" with Guid.NewGuid().ToString().
        // stateInitializer is called once per session to define the scope for the memory provider.
        stateInitializer: _ => new(new FoundryMemoryProviderScope("claw-sample-user")),
        new FoundryMemoryProviderOptions()
        {
            // For demo purposes, configure the memory provider to extract facts immediately
            // from each message. In a real-world scenario, you may want to set this to a higher value.
            UpdateDelay = 0,
        });

    // Create the memory store on first use (no-op if it already exists).
    await foundryMemory.EnsureMemoryStoreCreatedAsync(
        deploymentName,
        embeddingModel,
        "Durable memory for the Build-your-own-claw finance assistant.");

    Console.WriteLine($"Foundry memory enabled (store: {memoryStoreName}).");
}
else
{
    Console.WriteLine("Foundry memory disabled. Set FOUNDRY_MEMORY_STORE and FOUNDRY_EMBEDDING_MODEL to enable it.");
}
// </memory>

// <create_agent>
// Turn the chat client into a HarnessAgent. On top of Post 1's defaults we point file access at a
// fixed folder, add our approval-gated place_trade tool, and (optionally) wire in the Foundry
// memory provider for automatic, fine-grained fact extraction. File memory keeps its on-disk default
// store (see below), and we don't point it at a custom folder.
AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    // File access: read portfolio.csv and write reports under the sample's working/ folder.
    FileAccessStore = new FileSystemAgentFileStore(Path.Combine(AppContext.BaseDirectory, "working")),
    // Auto-approve the read-only file tools so reading portfolio.csv is frictionless, while saving,
    // deleting, and place_trade still pause for explicit approval.
    ToolApprovalAgentOptions = new ToolApprovalAgentOptions
    {
        AutoApprovalRules = [FileAccessProvider.ReadOnlyToolsAutoApprovalRule],
    },
    // Start in "execute" mode: this assistant is mostly quick lookups and single actions, so a plan
    // would be overkill. (Planning is still available — switch any time with /mode plan.)
    AgentModeProviderOptions = new AgentModeProviderOptions { DefaultMode = "execute" },
    // File memory is on by default. Its files live on disk under {cwd}/agent-file-memory/<session-id>/,
    // so they persist across runs on this machine. A brand-new session gets a new id (and so an empty
    // memory); /session-export and /session-import preserve the session's identity so a relaunched
    // session re-links to its existing on-disk memory files. The export file holds session state, not
    // the memory files themselves.
    // Fine-grained, automatic memory (when configured).
    AIContextProviders = foundryMemory is null ? null : [foundryMemory],
    ChatOptions = new ChatOptions
    {
        Instructions = instructions,
        Tools =
        [
            StockTools.CreateGetStockPriceTool(),
            TradingTools.CreatePlaceTradeTool(),
        ],
        Reasoning = new() { Effort = ReasoningEffort.Medium },
    },
});
// </create_agent>

// <run>
// Run the interactive console session. The default planning observers already include a tool
// approval observer, so the place_trade approval prompt is surfaced automatically.
await HarnessConsole.RunAgentAsync(
    agent,
    userPrompt: "Ask me to review your portfolio, draft a report, update your watchlist, or place a trade.",
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
