// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a HarnessAgent for interactive research tasks.
// The HarnessAgent comes pre-configured with TodoProvider, AgentModeProvider, FileMemoryProvider,
// ToolApproval, WebSearch, and OpenTelemetry — so this sample only needs custom instructions
// and a WebBrowsingTool.
// The agent plans research tasks, creates a todo list, gets user approval,
// and then executes each step — all within an interactive conversation loop.
//
// Special commands:
//   /todos  — Display the current todo list without invoking the agent.
//   /mode   — Get or set the current agent mode.
//   /exit   — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.Identity;
using Harness.Shared.Console;
using Harness.Shared.Console.ToolFormatters;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;

// Create a HarnessAgent with the Harness providers (TodoProvider and AgentModeProvider)
// and research-focused instructions including the mandatory planning workflow.
var instructions =
    """
    ## Research Assistant Instructions

    You are a research assistant. When given a research topic, research it thoroughly using web search and web browsing.
    Use your knowledge to form good search queries and hypotheses, but always verify claims with the tools available to you rather than relying on memory alone.

    ### Research quality

    Consult multiple sources when possible and cross-reference key claims.
    When sources disagree, note the discrepancy and explain which source you consider more reliable and why.
    If a web page fails to load or a search returns irrelevant results, try alternative search queries or sources before moving on.
    Track your sources — you will need them when presenting results.

    ### Presenting results

    When presenting your final findings:
    - Use Markdown formatting for clarity.
    - Use clear sections with headings for each major topic or sub-question.
    - Cite your sources inline (e.g., "According to [source name](URL), ...").
    - End with a brief summary of key takeaways.
    - In addition to returning the results to the user, save the final research report to file memory so it survives compaction and can be referenced later.
    """;

// Create the agent using AsHarnessAgent, which pre-configures function invocation,
// per-service-call chat history persistence, in-loop compaction, TodoProvider, AgentModeProvider,
// FileMemoryProvider, ToolApproval, WebSearch, AgentSkillsProvider, and OpenTelemetry.
// Only custom instructions, a WebBrowsingTool, and FileAccess opt-out are needed.
AIAgent agent =
    // Create an OpenAIClient that communicates with the Foundry responses service.
    new OpenAIClient(
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions()
        {
            Endpoint = new Uri(endpoint),
            RetryPolicy = new ClientRetryPolicy(3)          // Enable retries to improve resiliency.
        })
    .GetResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(deploymentName)  // We want to manage chat history locally (not stored in the responses service), so that we can manage compaction ourselves.
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "ResearchAgent",
        Description = "A research assistant that plans and executes research tasks.",
        DisableFileMemory = true,                           // If enabled, this would allow the agent to store memories as files in a directory associated with the current session
        FileMemoryStore = new FileSystemAgentFileStore(     // Configure the file memory provider to store files in a local folder called "agent-files".
            Path.Combine(AppContext.BaseDirectory, "agent-files")),
        ChatOptions = new ChatOptions
        {
            Instructions = instructions,
            Tools =
            [
                new WebBrowsingTool(                        // Add a local web browsing tool that converts html to markdown.
                    new WebBrowsingToolOptions { AllowPublicNetworks = true }),
            ],
            MaxOutputTokens = MaxOutputTokens,              // Set a high token limit for long research tasks with many tool calls and long outputs.
            Reasoning = new() { Effort = ReasoningEffort.Medium },
        },
    });

// Run the interactive console session using the shared HarnessConsole helper.
await HarnessConsole.RunAgentAsync(
    agent,
    userPrompt: "Enter a research topic to get started.",
    new HarnessConsoleOptions
    {
        Observers = [
            new OpenAIResponsesWebSearchDisplayObserver(),
            .. HarnessConsoleOptions.BuildObserversWithPlanning(
                agent,
                planModeName: "plan",
                executionModeName: "execute",
                maxContextWindowTokens: MaxContextWindowTokens,
                maxOutputTokens: MaxOutputTokens,
                toolFormatters: [new DownloadUriToolFormatter(), .. ToolCallFormatter.BuildDefaultToolFormatters()])],
        CommandHandlers = HarnessConsoleOptions.BuildDefaultCommandHandlers(agent),
    });
