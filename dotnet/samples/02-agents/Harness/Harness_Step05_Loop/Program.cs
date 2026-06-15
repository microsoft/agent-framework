// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to wrap a HarnessAgent with the LoopAgent decorator to re-invoke
// the agent until a configured LoopEvaluator decides to stop. It covers the common looping patterns
// through one decorator, each driven by a different evaluator:
//
//   1. Completion-marker (Ralph-style) loop — keep refining until the agent emits a completion
//      marker, restarting each pass from a fresh context (CompletionMarkerLoopEvaluator +
//      FreshContextPerIteration).
//   2. Delegate predicate (todos remaining) — loop while the built-in TodoProvider still has open
//      items (DelegateLoopEvaluator).
//   3. AI judge — a second chat client decides whether the original request was answered, and the
//      loop continues while the answer is "no" (AIJudgeLoopEvaluator).
//   4. Approval heuristics + loop — combine the LoopAgent with the ToolApprovalAgent auto-approval
//      heuristics so a looped agent auto-approves tool calls instead of stalling on approval.
//
// The demos run sequentially and print each loop's final response.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

// The HarnessAgent pre-configures function invocation, per-service-call chat history persistence, and
// context-window compaction. These bounds size the in-loop compaction window.
const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 32_000;

// Build a single Foundry-backed IChatClient factory shared by every demo. Each call returns a fresh
// IChatClient over the same Responses endpoint.
var projectClient = new AIProjectClient(
    new Uri(endpoint),
    // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
    // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
    // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
    new DefaultAzureCredential(),
    new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) });

IChatClient CreateChatClient() =>
    projectClient.GetProjectOpenAIClient().GetResponsesClient().AsIChatClient(deploymentName);

await RalphLoopAsync();
await TodoLoopAsync();
await JudgeLoopAsync();
await ApprovalLoopAsync();

// Pattern 1: a "Ralph"-style loop that refines until the agent signals completion.
async Task RalphLoopAsync()
{
    Console.WriteLine("\n=== 1. Completion-marker (Ralph-style) loop — refine until <promise>COMPLETE</promise> (max 5) ===");

    // Build a lean HarnessAgent: no todo or mode providers for this iterative-refinement task.
    AIAgent harnessAgent = CreateLeanHarnessAgent(
        name: "ralph",
        instructions:
            """
            You are iteratively refining a product name for a note-taking app. Each turn, build on the
            feedback so far: propose an improved candidate with a short reason. When you are confident the
            name is final, end your message with the exact marker <promise>COMPLETE</promise>.
            """);

    // CompletionMarkerLoopEvaluator stops once the marker appears in the response; until then it
    // re-invokes the agent. FreshContextPerIteration restarts each pass from the original task plus the
    // aggregated feedback log on a brand-new session. Because each pass starts fresh, the agent has no
    // memory of its prior suggestion — so the feedback template includes the {last_response} placeholder
    // to echo the previous candidate back to it.
    AIAgent loopAgent = new LoopAgent(
        harnessAgent,
        new CompletionMarkerLoopEvaluator("<promise>COMPLETE</promise>", options: new()
        {
            FeedbackMessageTemplate =
                "Your previous suggestion was:\n" + CompletionMarkerLoopEvaluator.LastResponsePlaceholder +
                "\n\nContinue to refine the name and remember to reply with " +
                CompletionMarkerLoopEvaluator.CompletionMarkerPlaceholder + " when happy.",
        }),
        new LoopAgentOptions { MaxIterations = 5, FreshContextPerIteration = true });

    AgentResponse response = await StreamLoopAsync(loopAgent, "Suggest a name for a note-taking app.");
    Console.WriteLine($"\nFinal response:\n{response.Text}");
}

// Pattern 2: loop while the built-in TodoProvider still has open items.
async Task TodoLoopAsync()
{
    Console.WriteLine("\n=== 2. Delegate predicate — loop while todos remain (max 6) ===");

    // Keep the built-in TodoProvider enabled (only the mode provider is disabled) so the agent has
    // todo tools to plan and track work.
    AIAgent harnessAgent = CreateLeanHarnessAgent(
        name: "planner",
        instructions:
            """
            You are a planning assistant. First break the task into todo items using your todo tools.
            Then, on each turn, make progress and mark completed items as done. When all items are
            complete, summarize the result.
            """,
        disableTodoProvider: false);

    // The predicate re-invokes the agent while any todo item is still open. The evaluator fetches the
    // built-in TodoProvider from context.Agent (via GetService, which forwards through the harness
    // decorators to the underlying ChatClientAgent's context providers), keeping the delegate
    // self-contained, then queries it against the loop's current session. When items remain, it returns
    // feedback telling the agent to finish them. MaxIterations guarantees the loop stops even if the
    // agent stalls.
    AIAgent loopAgent = new LoopAgent(
        harnessAgent,
        new DelegateLoopEvaluator(async (context, cancellationToken) =>
        {
            var todoProvider = context.Agent.GetService<TodoProvider>()
                ?? throw new InvalidOperationException("The agent did not expose a TodoProvider.");
            var remaining = await todoProvider.GetRemainingTodosAsync(context.Session).ConfigureAwait(false);
            return remaining.Count > 0
                ? LoopEvaluation.Continue($"Not all todos are complete yet ({remaining.Count} remaining). Please complete the remaining todo items.")
                : LoopEvaluation.Stop();
        }),
        new LoopAgentOptions { MaxIterations = 6 });

    // The LoopAgent creates a single session up front and reuses it across iterations (non-fresh
    // mode), so the todo state persists; the predicate reads it via context.Session.
    AgentResponse response = await StreamLoopAsync(
        loopAgent,
        "Plan and outline a 3-section blog post about Rayleigh scattering.");
    Console.WriteLine($"\nFinal response:\n{response.Text}");
}

// Pattern 3: a second chat client judges whether the original request was answered.
async Task JudgeLoopAsync()
{
    Console.WriteLine("\n=== 3. AI judge — loop until the request is answered (max 4) ===");

    AIAgent harnessAgent = CreateLeanHarnessAgent(
        name: "answerer",
        instructions: "You are a helpful assistant. Answer the user's question thoroughly.");

    // The judge uses its own IChatClient. AIJudgeLoopEvaluator asks it (via a JudgeVerdict structured
    // output) whether the original request has been fully addressed and continues while the answer is
    // "no", injecting the judge's gap analysis as the next iteration's input. Judge loops use a small
    // MaxIterations cap because each pass costs an extra model call.
    AIAgent loopAgent = new LoopAgent(
        harnessAgent,
        new AIJudgeLoopEvaluator(CreateChatClient()),
        new LoopAgentOptions { MaxIterations = 4 });

    AgentResponse response = await StreamLoopAsync(
        loopAgent,
        "Explain why the sky is blue, then also explain why sunsets are red.");
    Console.WriteLine($"\nFinal response:\n{response.Text}");
}

// Pattern 4: combine the loop with the ToolApprovalAgent auto-approval heuristics.
async Task ApprovalLoopAsync()
{
    Console.WriteLine("\n=== 4. Approval heuristics + loop — auto-approve tool calls in the loop (max 2) ===");

    var deployTool = new ApprovalRequiredAIFunction(
        AIFunctionFactory.Create(DeploymentTools.DeployService));

    // Configure the HarnessAgent's built-in ToolApprovalAgent with an auto-approval rule. The rule
    // approves the deploy_service call without prompting, so the inner agent resolves the approval
    // internally and never surfaces a pending approval to the LoopAgent — letting the loop proceed.
    AIAgent harnessAgent = CreateLeanHarnessAgent(
        name: "operator",
        instructions: "You are a deployment operator. Use the DeployService tool to fulfil requests.",
        tools: [deployTool],
        toolApprovalAgentOptions: new ToolApprovalAgentOptions
        {
            AutoApprovalRules =
            [
                functionCall =>
                {
                    Console.WriteLine($"  Auto-approving: {functionCall.Name}");
                    return ValueTask.FromResult(true);
                },
            ],
        });

    // Drive a short loop that continues until the response confirms the deployment.
    AIAgent loopAgent = new LoopAgent(
        harnessAgent,
        new DelegateLoopEvaluator((context, _) =>
            new ValueTask<LoopEvaluation>(
                context.LastResponse.Text.Contains("deployed", StringComparison.OrdinalIgnoreCase)
                    ? LoopEvaluation.Stop()
                    : LoopEvaluation.Continue())),
        new LoopAgentOptions { MaxIterations = 2 });

    // The LoopAgent reuses a single session across iterations, so the approval response flows back in.
    AgentResponse response = await StreamLoopAsync(loopAgent, "Deploy the billing service.");
    Console.WriteLine($"\nFinal response:\n{response.Text}");
}

// Streams a loop run to the console, printing updates live and marking each new inner run (detected
// via a change in ResponseId) with an "--- run N ---" header so you can see when the LoopAgent
// re-invokes the inner agent. Each message is prefixed with "User:" or "Agent:" based on its role, so
// the loop's on-behalf-of feedback (User) is visually distinct from the agent's responses (Agent).
// Returns the aggregated final response.
static async Task<AgentResponse> StreamLoopAsync(AIAgent loopAgent, string input, AgentSession? session = null)
{
    string? currentResponseId = null;
    ChatRole? currentRole = null;
    var runCount = 0;
    var updates = new List<AgentResponseUpdate>();

    await foreach (var update in loopAgent.RunStreamingAsync(input, session))
    {
        // A new ResponseId signals the start of another inner run (loop iteration).
        if (update.ResponseId is { } responseId && responseId != currentResponseId)
        {
            currentResponseId = responseId;
            currentRole = null;
            Console.WriteLine($"\n--- run {++runCount} ---");
        }

        // Print a role-based prefix whenever the speaker changes — for example the loop's on-behalf-of
        // user feedback versus the agent's response.
        if (update.Role is { } role && role != currentRole)
        {
            currentRole = role;
            var prefix = role == ChatRole.User ? "User" : role == ChatRole.Assistant ? "Agent" : role.Value;
            Console.Write($"\n{prefix}: ");
        }

        Console.Write(update.Text);
        updates.Add(update);
    }

    Console.WriteLine();
    return updates.ToAgentResponse();
}

// Creates a HarnessAgent with the agent-mode provider always disabled (and the todo provider disabled
// by default), plus all other heavyweight providers turned off so each loop demo stays focused.
AIAgent CreateLeanHarnessAgent(
    string name,
    string instructions,
    bool disableTodoProvider = true,
    IList<AITool>? tools = null,
    ToolApprovalAgentOptions? toolApprovalAgentOptions = null) =>
    CreateChatClient().AsHarnessAgent(new HarnessAgentOptions
    {
        Name = name,
        MaxContextWindowTokens = MaxContextWindowTokens,
        MaxOutputTokens = MaxOutputTokens,
        DisableAgentModeProvider = true,
        DisableTodoProvider = disableTodoProvider,
        DisableFileMemory = true,
        DisableFileAccess = true,
        DisableWebSearch = true,
        ToolApprovalAgentOptions = toolApprovalAgentOptions,
        ChatOptions = new ChatOptions
        {
            Instructions = instructions,
            Tools = tools,
            MaxOutputTokens = MaxOutputTokens,
        },
    });

/// <summary>Tool used by the approval-handling demo.</summary>
internal static class DeploymentTools
{
    [Description("Deploy a service to production (requires approval).")]
    public static string DeployService([Description("The name of the service to deploy.")] string service) =>
        $"Deployed {service} to production.";
}
