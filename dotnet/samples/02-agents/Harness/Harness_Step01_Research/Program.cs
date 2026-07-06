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
using Azure.AI.Projects;
using Azure.Identity;
using Harness.Shared.Console;
using Harness.Shared.Console.OpenAI;
using Harness.Shared.Console.ToolFormatters;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;
const string TracingSourceName = "Harness.Research";

// Set up OpenTelemetry tracing that writes spans to a text file.
// This captures all agent activity (tool calls, model invocations, compaction, etc.)
// as well as HTTP requests made by the underlying HttpClient transport.
using var tracerProvider = HarnessTracing.CreateFileTracerProvider(TracingSourceName);

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
    new AIProjectClient(
        new Uri(endpoint),
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })  // Enable retries to improve resiliency.
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(new HarnessAgentOptions
    {
        MaxContextWindowTokens = MaxContextWindowTokens,
        MaxOutputTokens = MaxOutputTokens,
        Name = "ResearchAgent",
        Description = "A research assistant that plans and executes research tasks.",
        DisableFileAccess = true,                           // If enabled, this would allow the agent to read/write files in a working directory
        OpenTelemetrySourceName = TracingSourceName,        // Use our custom source name so spans are captured by the TracerProvider above.
        FileMemoryStore = new FileSystemAgentFileStore(     // Configure the file memory provider to store files in a local folder called "agent-files".
            Path.Combine(AppContext.BaseDirectory, "agent-files")),
        // The built in ModeProvider has two default modes: "plan" and "execute".
        // Adding a loop evaluator so that in "execute" mode, the harness keeps re-invoking itself until every todo item is complete.
        LoopEvaluators =
        [
            new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = ["execute"] }),
        ],
        LoopAgentOptions = new LoopAgentOptions { MaxIterations = 10 }, // Safety cap on the number of autonomous passes per turn.
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
            new OpenAIResponsesErrorObserver(),
            .. HarnessConsoleOptions.BuildObserversWithPlanning(
                agent,
                planModeName: "plan",
                executionModeName: "execute",
                maxContextWindowTokens: MaxContextWindowTokens,
                maxOutputTokens: MaxOutputTokens,
                toolFormatters: [new DownloadUriToolFormatter(), .. ToolCallFormatter.BuildDefaultToolFormatters()])],
        CommandHandlers = HarnessConsoleOptions.BuildDefaultCommandHandlers(agent),
    });
