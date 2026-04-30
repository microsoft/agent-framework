// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a coding-style agent that operates over a real on-disk workspace
// using FileSystemToolProvider. It composes:
//
//   - FileSystemToolProvider — universal FileAccess_* tools plus high-fidelity fs_* tools
//     (line-range view, unique-match edits, atomic batched edits, gitignore-aware glob/grep,
//     recursive list, approval-gated mutations).
//   - TodoProvider          — agent-tracked task list to coordinate multi-step coding work.
//   - AgentModeProvider     — plan/execute mode switching for review-before-edit workflows.
//   - ToolApprovalAgent     — approval gating for destructive operations (Delete, Move, Rename),
//                             with persistent allow rules per session.
//
// The agent operates inside a sandboxed `workspace/` folder that ships with the sample. Symlink
// traversal is rejected and secrets-like paths (e.g. .env, *.pem) are blocked by default.
//
// Special commands:
//   exit — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.Identity;
using Harness.Shared.Console;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;

// Point the workspace at the folder that ships with the sample. The provider creates it if missing.
var workspace = Path.Combine(AppContext.BaseDirectory, "workspace");
Directory.CreateDirectory(workspace);

var instructions =
    $$"""
    You are a coding assistant operating inside a sandboxed workspace at `{{workspace}}`.

    ## Tools
    You have two complementary file-tool surfaces:

    - `FileAccess_*` (universal): SaveFile, ReadFile, DeleteFile, ListFiles, SearchFiles. Use for simple whole-file work.
    - `fs_*` (high-fidelity): fs_view (line ranges), fs_edit (unique-match), fs_multi_edit (atomic batch),
      fs_glob, fs_grep, fs_list_dir, fs_move, fs_rename. Prefer these for source code edits and navigation.

    Destructive operations (FileAccess_DeleteFile, fs_move, fs_rename) require user approval.
    Once approved with "always allow", subsequent calls in the same session run automatically.

    ## Workflow
    1. Plan first. Use the todo tools to break the task into small, verifiable steps.
    2. Explore before editing. Use fs_list_dir, fs_glob, and fs_grep to find the files you need.
    3. Read with line ranges (fs_view) and apply minimal edits with fs_edit / fs_multi_edit.
    4. Never overwrite or delete files outside what the user asked for.
    5. Summarize what you did and which files changed at the end of each task.
    """;

var compactionStrategy = new ContextWindowCompactionStrategy(
    maxContextWindowTokens: MaxContextWindowTokens,
    maxOutputTokens: MaxOutputTokens);

AIAgent agent =
    new OpenAIClient(
        new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions()
        {
            Endpoint = new Uri(endpoint),
            RetryPolicy = new ClientRetryPolicy(3)
        })
    .GetResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(deploymentName)

    .AsBuilder()
    .UseFunctionInvocation()
    .UsePerServiceCallChatHistoryPersistence()
    .UseAIContextProviders(new CompactionProvider(compactionStrategy))

    .BuildAIAgent(
        new ChatClientAgentOptions
        {
            Name = "CodingAgent",
            Description = "A sandboxed coding assistant that edits files in a workspace folder.",
            UseProvidedChatClientAsIs = true,
            RequirePerServiceCallChatHistoryPersistence = true,
            ChatHistoryProvider = new InMemoryChatHistoryProvider(
                new InMemoryChatHistoryProviderOptions
                {
                    ChatReducer = compactionStrategy.AsChatReducer(),
                }),
            AIContextProviders =
            [
                new TodoProvider(),
                new AgentModeProvider(),
                // Hardened, on-disk file provider. Inherits the universal FileAccess_* surface
                // and adds high-fidelity fs_* tools. Symlink rejection and the secrets denylist
                // are on by default.
                new FileSystemToolProvider(workspace),
            ],
            ChatOptions = new ChatOptions
            {
                Instructions = instructions,
                MaxOutputTokens = MaxOutputTokens,
                Reasoning = new() { Effort = ReasoningEffort.Medium },
            },
        })
    .AsBuilder()
    .UseToolApproval()
    .Build();

await HarnessConsole.RunAgentAsync(
    agent,
    title: "Coding Agent",
    userPrompt: "Ask me to read, search, refactor, or edit files in the workspace folder.",
    new HarnessConsoleOptions
    {
        MaxContextWindowTokens = MaxContextWindowTokens,
        MaxOutputTokens = MaxOutputTokens,
        EnablePlanningUx = true,
        PlanningModeName = "plan",
        ExecutionModeName = "execute"
    });
