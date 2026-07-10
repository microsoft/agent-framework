// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a HarnessAgent with ALL features enabled, plus:
// - Hyperlight CodeAct (HyperlightCodeActProvider) for sandboxed Python code execution
// - Skills (AgentSkillsProvider) discovering a local "regex-tester" skill
//
// The agent can plan tasks with todos, manage modes, store memories, read/write files,
// search the web, approve sensitive tools, discover and use skills, and execute arbitrary
// Python code in a Hyperlight sandbox — all pre-configured by the HarnessAgent.
//
// Try asking: "Help me write a regex that matches valid email addresses, then test it."
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
using HyperlightSandbox.Guest.Python;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hyperlight;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;
const string TracingSourceName = "Harness.CodeExecution";

// Set up OpenTelemetry tracing that writes spans to a text file.
using var tracerProvider = HarnessTracing.CreateFileTracerProvider(TracingSourceName);

// Create the HyperlightCodeActProvider with the Python/Wasm backend.
// The guest module path is resolved automatically from the Hyperlight.HyperlightSandbox.Guest.Python NuGet package.
using var codeAct = new HyperlightCodeActProvider(
    HyperlightCodeActProviderOptions.CreateForWasm(PythonGuestModule.GetModulePath()));

var instructions =
    """
    ## Technical Assistant Instructions

    You are a code-powered technical assistant. You can execute Python code in a sandboxed environment
    to solve problems precisely rather than guessing. You also have access to skills that provide
    structured workflows for specific technical tasks.

    ### Code Execution

    When a problem requires computation, validation, or testing:
    - Write Python code and use `execute_code` to run it in the sandbox.
    - Always verify results by running the code rather than reasoning about what would happen.
    - If code fails, read the error message carefully, fix the issue, and retry.

    ### Skills

    You have access to discoverable skills. When a task matches a skill's description:
    - Follow the skill's instructions carefully.
    - Use the skill's reference materials for context.
    - Combine the skill's workflow with code execution when appropriate.

    ### Planning and Research

    For complex tasks:
    - Break the problem into steps using your todo list.
    - Research background information using web search when needed.
    - Save important findings to file memory for later reference.

    ### Presenting Results

    - Show your work: include the code you ran and its output.
    - Explain what each part of your solution does.
    - If applicable, save final results to file memory.
    """;

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// Create the agent with ALL HarnessAgent features enabled plus Hyperlight CodeAct.
// No Disable* flags are set — TodoProvider, AgentModeProvider, FileMemory, FileAccess,
// ToolApproval, WebSearch, and AgentSkillsProvider are all active.
AIAgent agent =
    new AIProjectClient(
        new Uri(endpoint),
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(new HarnessAgentOptions
    {
        MaxContextWindowTokens = MaxContextWindowTokens,
        MaxOutputTokens = MaxOutputTokens,
        Name = "CodeExecutionAgent",
        Description = "A technical assistant with sandboxed code execution and skill-based workflows.",
        OpenTelemetrySourceName = TracingSourceName,
        // Point the file memory at a local folder for persistent memory across sessions.
        FileMemoryStore = new FileSystemAgentFileStore(Path.Combine(AppContext.BaseDirectory, "agent-files")),
        // Add the HyperlightCodeActProvider so the agent can execute Python code in a sandbox.
        AIContextProviders = [codeAct],
        ChatOptions = new ChatOptions
        {
            Instructions = instructions,
            MaxOutputTokens = MaxOutputTokens,
            Reasoning = new() { Effort = ReasoningEffort.Medium },
        },
    });

// Run the interactive console session using the shared HarnessConsole helper.
await HarnessConsole.RunAgentAsync(
    agent,
    userPrompt: "Ask me a technical question, or try: \"Help me write a regex that matches valid email addresses.\"",
    new HarnessConsoleOptions
    {
        Observers = HarnessConsoleOptions.BuildObserversWithPlanning(
            agent,
            planModeName: "plan",
            executionModeName: "execute",
            maxContextWindowTokens: MaxContextWindowTokens,
            maxOutputTokens: MaxOutputTokens),
        CommandHandlers = HarnessConsoleOptions.BuildDefaultCommandHandlers(agent),
    });
