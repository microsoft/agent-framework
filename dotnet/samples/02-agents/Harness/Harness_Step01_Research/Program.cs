// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a HarnessAgent with the Harness AIContextProviders
// (TodoProvider and AgentModeProvider) for interactive research tasks with web search
// capabilities powered by Azure AI Foundry.
// The agent plans research tasks, creates a todo list, gets user approval,
// and then executes each step — all within an interactive conversation loop.
//
// Special commands:
//   /todos  — Display the current todo list without invoking the agent.
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
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;

// Create a HarnessAgent with the Harness providers (TodoProvider and AgentModeProvider)
// and research-focused instructions including the mandatory planning workflow.
var instructions =
    """
    You are a research assistant. When given a research topic, research it thoroughly using web search and web browsing.
    Use your knowledge to form good search queries and hypotheses, but always verify claims with the tools available to you rather than relying on memory alone.

    ## Mandatory planning workflow

    For every new substantive user request, including short factual questions, your behavior is determined by the mode you are in.
    If you are in plan mode, start with the *Plan Mode* steps, and if you are in execute mode, skip directly to the *Execute Mode* steps below.

    *Plan Mode*

    1. Analyze the request with the purpose of building a research plan.
    2. Create a list of todo items.
    3. If needed, use the provided tools to do some exploratory checks to help build a plan and determine what clarifying questions you may need from the user.
    4. Ask for clarifications from the user where needed.
      1. Ask each clarification one by one.
      2. When asking for clarification and you have specific options in mind, present them to the user, so they can choose the option instead of having to retype the entire response.
      3. Do not proceed until you have received all the needed clarifications.
      4. Do short exploratory research if it helps with being able to ask sensible clarifications from the user.
    5. Write the plan to a memory file, so that it is retained even if compaction happens. Make sure to update the plan file if the user requests changes.
    6. Present the plan to the user and ask for approval to switch to execute mode and process the plan.
    7. When approval is granted, always switch to execute mode (using the `AgentMode_Set` tool), and follow the steps for *Execute mode*.

    *Execute Mode*

    1. If you don't have a plan or tasks yet, analyse the user request and create tasks and a plan. (**Skip this step if you came from plan mode**)
    2. Work autonomously — use your best judgement to make decisions and keep progressing without asking the user questions. The goal is to have a complete, useful result ready when the user returns.
    3. If you encounter ambiguity or an unexpected situation during execution, choose the most reasonable option, note your choice, and keep going.
    4. Mark tasks as completed as you finish them.
    5. Continue working, thinking and calling tools until you have the research result for the user.

    ## General Instructions

    - You must check the current mode after any user input, since the user may have changed the mode themselves,
      e.g. the user may have switched to 'plan' mode after a previous research task finished in 'execute' mode, meaning they want to review a plan first before execution.
    - Explain your reasoning and thought process as you work through tasks.
    - Explain what you learned and what you are going to do next between tool calls, so the user can follow along with your thought process.
    - Avoid making more than 4 tool calls in a row without explaining what you are doing.
    - Do not answer the underlying question before the plan has been presented and approved.
    - This rule applies even when the answer seems obvious or the task seems small.
    - For short requests, use a brief micro-plan rather than skipping planning. The only exceptions are:
      - greetings,
      - pure acknowledgments,
      - clarification questions needed to form the plan,
      - follow-up questions about results you have already presented,
      - meta-discussion about the workflow itself.

    **Todo management**

    Mark each todo complete as you finish it so the list stays current.
    If a todo turns out to be unnecessary or is blocked, remove it and briefly explain why.
    Once the user finishes with a topic and moves onto a new one, clean up old completed todos by deleting them.

    **Research quality**

    Consult multiple sources when possible and cross-reference key claims.
    When sources disagree, note the discrepancy and explain which source you consider more reliable and why.
    If a web page fails to load or a search returns irrelevant results, try alternative search queries or sources before moving on.
    Track your sources — you will need them when presenting results.

    **Presenting results**

    When presenting your final findings:
    - Use clear sections with headings for each major topic or sub-question.
    - Cite your sources inline (e.g., "According to [source name](URL), ...").
    - End with a brief summary of key takeaways.
    - Save the final research report to file memory so it survives compaction and can be referenced later.

    **File memory**

    Use the FileMemory_* tools to:
    - Store downloaded search results or web pages.
    - Store plans.
    - Read the current plan to make sure tasks were done according to plan.
    - Store findings.
    - Check for relevant previously downloaded data / findings before starting new research.
    """;

// Create the agent using AsHarnessAgent, which pre-configures function invocation,
// per-service-call chat history persistence, and in-loop compaction.
// Then wrap with UseToolApproval to allow auto-approving tools once confirmed.
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
    .AsIChatClientWithStoredOutputDisabled(deploymentName)   // We want to manage chat history locally (not stored in the responses service), so that we can manage compaction ourselves.
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "ResearchAgent",
        Description = "A research assistant that plans and executes research tasks.",
        AIContextProviders =
        [
            new TodoProvider(),         // Add an AIContextProvider to allow the agent to create a TODO list, which is stored in the session.
            new AgentModeProvider(),    // Add an AIContextProvider that tracks the agent mode and allows switching mode. Current mode is stored in the session.
            new FileMemoryProvider(     // Add an AIContextProvider that can store memories in files under a session specific working folder.
                new FileSystemAgentFileStore(Path.Combine(AppContext.BaseDirectory, "agent-files")),
                (_) => new FileMemoryState() { WorkingFolder = DateTime.UtcNow.ToString("yyyyMMdd_HHmmss") + "_" + Guid.NewGuid().ToString() })
        ],
        ChatOptions = new ChatOptions
        {
            Instructions = instructions,
            Tools =
            [
                ResponseTool.CreateWebSearchTool().AsAITool(),          // Add the foundry hosted web search tool that runs in the service.
                new WebBrowsingTool(                                    // Add a local web browsing tool that converts html to markdown.
                    new WebBrowsingToolOptions { AllowPublicNetworks = true }),
            ],
            MaxOutputTokens = MaxOutputTokens,                          // Set a high token limit for long research tasks with many tool calls and long outputs.
            Reasoning = new() { Effort = ReasoningEffort.Medium },
        },
    })
    .AsBuilder()
    .UseToolApproval()                                                      // Add the ability to auto approve tools once a user has said they don't want to be asked again. Approval rules are tied to the session.
    .Build();

// Run the interactive console session using the shared HarnessConsole helper.
await HarnessConsole.RunAgentAsync(
    agent,
    title: "Research Assistant",
    userPrompt: "Enter a research topic to get started.",
    new HarnessConsoleOptions
    {
        MaxContextWindowTokens = MaxContextWindowTokens,
        MaxOutputTokens = MaxOutputTokens,
        EnablePlanningUx = true,
        PlanningModeName = "plan",
        ExecutionModeName = "execute"
    });
