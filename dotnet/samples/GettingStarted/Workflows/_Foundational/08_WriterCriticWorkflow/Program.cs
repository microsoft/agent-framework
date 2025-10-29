// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using System.Text;
using System.Text.Json;

namespace WriterCriticWorkflow;

/// <summary>
/// This sample demonstrates an iterative refinement workflow between Writer and Critic agents.
///
/// The workflow implements a content creation and review loop that:
/// 1. Writer creates initial content based on the user's request
/// 2. Critic reviews the content and provides feedback
/// 3. If approved: Summary executor presents the final content
/// 4. If rejected: Writer revises based on feedback (loops back)
/// 5. Continues until approval or max iterations (3) is reached
///
/// This pattern is useful when you need:
/// - Iterative content improvement through feedback loops
/// - Quality gates with reviewer approval
/// - Maximum iteration limits to prevent infinite loops
/// - Conditional workflow routing based on agent decisions
///
/// Key Learning: Workflows can implement loops with conditional edges and shared state
/// to track iteration progress across multiple executor invocations.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Previous foundational samples should be completed first.
/// - An Azure OpenAI chat completion deployment must be configured.
/// </remarks>
public static class Program
{
    public const int MaxIterations = 3;

    private static async Task Main()
    {
        Console.WriteLine("\n=== Writer-Critic Iteration Workflow ===\n");
        Console.WriteLine($"Writer and Critic will iterate up to {MaxIterations} times until approval.\n");

        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

        // Create executors for content creation and review
        WriterExecutor writer = new(chatClient);
        CriticExecutor critic = new(chatClient);
        SummaryExecutor summary = new(chatClient);

        // Build the workflow with conditional routing based on critic's decision
        // Key Point: The workflow loops back to Writer if content is rejected,
        // or proceeds to Summary if approved. State tracking ensures we don't loop forever.
        WorkflowBuilder workflowBuilder = new WorkflowBuilder(writer)
            .AddEdge(writer, critic)
            .AddSwitch(critic, sw => sw
                .AddCase<CriticDecision>(cd => cd?.Approved == true, summary)
                .AddCase<CriticDecision>(cd => cd?.Approved == false, writer))
            .WithOutputFrom(summary);

        // Execute the workflow with a sample task
        Console.WriteLine(new string('=', 80));
        Console.WriteLine("TASK: Write a short blog post about AI ethics (200 words)");
        Console.WriteLine(new string('=', 80) + "\n");

        const string InitialTask = "Write a 200-word blog post about AI ethics. Make it thoughtful and engaging.";

        // Build a fresh workflow for execution
        Workflow workflow = workflowBuilder.Build();
        await ExecuteWorkflowAsync(workflow, InitialTask);

        Console.WriteLine("\n✅ Sample Complete: Writer-Critic iteration demonstrates conditional workflow loops\n");
        Console.WriteLine("Key Concepts Demonstrated:");
        Console.WriteLine("  ✓ Iterative refinement loop with conditional routing");
        Console.WriteLine("  ✓ Shared workflow state for iteration tracking");
        Console.WriteLine($"  ✓ Max iteration cap ({MaxIterations}) for safety");
        Console.WriteLine("  ✓ Multiple message handlers in a single executor");
        Console.WriteLine("  ✓ Streaming support for real-time feedback\n");
    }

    private static async Task ExecuteWorkflowAsync(Workflow workflow, string input)
    {
        // Execute in streaming mode to see real-time progress
        await using StreamingRun run = await InProcessExecution.StreamAsync<string>(workflow, input);

        // Watch the workflow events
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            switch (evt)
            {
                case AgentRunUpdateEvent agentUpdate:
                    // Stream agent output in real-time (optional, controlled by ShowAgentThinking)
                    if (!string.IsNullOrEmpty(agentUpdate.Update.Text))
                    {
                        Console.Write(agentUpdate.Update.Text);
                    }
                    break;

                case WorkflowOutputEvent output:
                    Console.WriteLine("\n\n" + new string('=', 80));
                    Console.ForegroundColor = ConsoleColor.Green;
                    Console.WriteLine("✅ FINAL APPROVED CONTENT");
                    Console.ResetColor();
                    Console.WriteLine(new string('=', 80));
                    Console.WriteLine();
                    Console.WriteLine(output.Data);
                    Console.WriteLine();
                    Console.WriteLine(new string('=', 80));
                    break;
            }
        }
    }
}

// ====================================
// Shared State for Iteration Tracking
// ====================================

/// <summary>
/// Tracks the current iteration and conversation history across workflow executions.
/// </summary>
internal sealed class FlowState
{
    public int Iteration { get; set; } = 1;
    public List<ChatMessage> History { get; } = [];
}

/// <summary>
/// Constants for accessing the shared flow state in workflow context.
/// </summary>
internal static class FlowStateShared
{
    public const string Scope = "FlowStateScope";
    public const string Key = "singleton";
}

/// <summary>
/// Helper methods for reading and writing shared flow state.
/// </summary>
internal static class FlowStateHelpers
{
    public static async Task<FlowState> ReadFlowStateAsync(IWorkflowContext context)
    {
        FlowState? state = await context.ReadStateAsync<FlowState>(FlowStateShared.Key, scopeName: FlowStateShared.Scope);
        return state ?? new FlowState();
    }

    public static ValueTask SaveFlowStateAsync(IWorkflowContext context, FlowState state)
        => context.QueueStateUpdateAsync(FlowStateShared.Key, state, scopeName: FlowStateShared.Scope);
}

// ====================================
// Data Transfer Objects
// ====================================

/// <summary>
/// Represents the critic's decision and feedback on the content.
/// </summary>
internal sealed class CriticDecision
{
    public bool Approved { get; set; }
    public string Feedback { get; set; } = "";
    public string Content { get; set; } = "";
    public int Iteration { get; set; }
}

// ====================================
// Custom Executors
// ====================================

/// <summary>
/// Executor that creates or revises content based on user requests or critic feedback.
/// This executor demonstrates multiple message handlers for different input types.
/// </summary>
internal sealed class WriterExecutor : Executor
{
    private readonly AIAgent _agent;

    public WriterExecutor(IChatClient chatClient) : base("Writer")
    {
        this._agent = new ChatClientAgent(
            chatClient,
            name: "Writer",
            instructions: """
                You are a skilled writer. Create clear, engaging content.
                If you receive feedback, carefully revise the content to address all concerns.
                Maintain the same topic and length requirements.
                """
        );
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder
            .AddHandler<string, ChatMessage>(this.HandleInitialRequestAsync)
            .AddHandler<CriticDecision, ChatMessage>(this.HandleRevisionRequestAsync);

    /// <summary>
    /// Handles the initial writing request from the user.
    /// </summary>
    private async ValueTask<ChatMessage> HandleInitialRequestAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        return await this.HandleAsyncCoreAsync(new ChatMessage(ChatRole.User, message), context, cancellationToken);
    }

    /// <summary>
    /// Handles revision requests from the critic with feedback.
    /// </summary>
    private async ValueTask<ChatMessage> HandleRevisionRequestAsync(
        CriticDecision decision,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        string prompt = "Revise the following content based on this feedback:\n\n" +
                       $"Feedback: {decision.Feedback}\n\n" +
                       $"Original Content:\n{decision.Content}";

        return await this.HandleAsyncCoreAsync(new ChatMessage(ChatRole.User, prompt), context, cancellationToken);
    }

    /// <summary>
    /// Core implementation for generating content (initial or revised).
    /// </summary>
    private async Task<ChatMessage> HandleAsyncCoreAsync(
        ChatMessage message,
        IWorkflowContext context,
        CancellationToken cancellationToken)
    {
        FlowState state = await FlowStateHelpers.ReadFlowStateAsync(context);

        Console.WriteLine($"\n=== Writer (Iteration {state.Iteration}) ===\n");

        StringBuilder sb = new();
        await foreach (AgentRunResponseUpdate update in this._agent.RunStreamingAsync(message, cancellationToken: cancellationToken))
        {
            if (!string.IsNullOrEmpty(update.Text))
            {
                sb.Append(update.Text);
                Console.Write(update.Text);
            }
        }
        Console.WriteLine("\n");

        string text = sb.ToString();
        state.History.Add(new ChatMessage(ChatRole.Assistant, text));
        await FlowStateHelpers.SaveFlowStateAsync(context, state);

        return new ChatMessage(ChatRole.User, text);
    }
}

/// <summary>
/// Executor that reviews content and decides whether to approve or request revisions.
/// Uses JSON output for structured decision-making.
/// </summary>
internal sealed class CriticExecutor : Executor<ChatMessage, CriticDecision>
{
    private readonly AIAgent _agent;

    public CriticExecutor(IChatClient chatClient) : base("Critic")
    {
        this._agent = new ChatClientAgent(
            chatClient,
            name: "Critic",
            instructions: """
                You are a constructive critic. Review the content and provide specific feedback.
                Always try to provide actionable suggestions for improvement and strive to identify improvement points.
                Only approve if the content is high quality, clear, and meets the original requirements and you see no improvement points.

                At the end, output EXACTLY one JSON line:
                {"approved":true,"feedback":""} if the content is good
                {"approved":false,"feedback":"<specific improvements needed>"} if revisions are needed
                
                Be concise but specific in your feedback.
                """
        );
    }

    public override async ValueTask<CriticDecision> HandleAsync(
        ChatMessage message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        FlowState state = await FlowStateHelpers.ReadFlowStateAsync(context);

        Console.WriteLine($"=== Critic (Iteration {state.Iteration}) ===\n");

        StringBuilder sb = new();
        await foreach (AgentRunResponseUpdate update in this._agent.RunStreamingAsync(message, cancellationToken: cancellationToken))
        {
            if (!string.IsNullOrEmpty(update.Text))
            {
                sb.Append(update.Text);
                Console.Write(update.Text);
            }
        }
        Console.WriteLine("\n");

        string fullResponse = sb.ToString();
        (bool approved, string feedback) = ParseDecision(fullResponse);

        // Safety: approve if max iterations reached
        if (!approved && state.Iteration >= Program.MaxIterations)
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine($"⚠️ Max iterations ({Program.MaxIterations}) reached - auto-approving");
            Console.ResetColor();
            approved = true;
            feedback = "";
        }

        // Increment iteration ONLY if rejecting (will loop back to Writer)
        if (!approved)
        {
            state.Iteration++;
        }

        state.History.Add(new ChatMessage(ChatRole.Assistant, StripTrailingJson(fullResponse)));
        await FlowStateHelpers.SaveFlowStateAsync(context, state);

        return new CriticDecision
        {
            Approved = approved,
            Feedback = feedback,
            Content = message.Text ?? "",
            Iteration = state.Iteration
        };
    }

    /// <summary>
    /// Parses the critic's response to extract the approval decision and feedback.
    /// Looks for a JSON line in the format: {"approved":true/false,"feedback":"..."}
    /// </summary>
    private static (bool approved, string feedback) ParseDecision(string fullResponse)
    {
        string? lastJson = null;
        foreach (string line in fullResponse.Replace("\r\n", "\n").Split('\n').Reverse())
        {
            string trimmedLine = line.Trim();
            if (trimmedLine.StartsWith('{') && trimmedLine.EndsWith('}'))
            {
                lastJson = trimmedLine;
                break;
            }
        }

        if (lastJson is null)
        {
            // Fallback: check for explicit approval text
            if (fullResponse.Contains("APPROVE", StringComparison.OrdinalIgnoreCase))
            {
                return (true, "");
            }
            return (false, "Missing approval decision.");
        }

        try
        {
            using JsonDocument doc = JsonDocument.Parse(lastJson);
            bool ok = doc.RootElement.GetProperty("approved").GetBoolean();
            string fb = doc.RootElement.TryGetProperty("feedback", out JsonElement el) ? el.GetString() ?? "" : "";
            return (ok, fb);
        }
        catch
        {
            return (false, "Malformed approval JSON.");
        }
    }

    /// <summary>
    /// Removes the trailing JSON decision line from the response for cleaner history.
    /// </summary>
    private static string StripTrailingJson(string text)
    {
        string[] lines = text.Replace("\r\n", "\n").Split('\n');
        if (lines.Length == 0)
        {
            return text;
        }

        string lastLine = lines[^1].Trim();
        if (lastLine.StartsWith('{') && lastLine.EndsWith('}'))
        {
            return string.Join("\n", lines[..^1]);
        }
        return text;
    }
}

/// <summary>
/// Executor that presents the final approved content to the user.
/// </summary>
internal sealed class SummaryExecutor : Executor<CriticDecision, ChatMessage>
{
    private readonly AIAgent _agent;

    public SummaryExecutor(IChatClient chatClient) : base("Summary")
    {
        this._agent = new ChatClientAgent(
            chatClient,
            name: "Summary",
            instructions: """
                You present the final approved content to the user.
                Simply output the polished content - no additional commentary needed.
                """
        );
    }

    public override async ValueTask<ChatMessage> HandleAsync(
        CriticDecision message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine("=== Summary ===\n");

        string prompt = $"Present this approved content:\n\n{message.Content}";

        StringBuilder sb = new();
        await foreach (AgentRunResponseUpdate update in this._agent.RunStreamingAsync(new ChatMessage(ChatRole.User, prompt), cancellationToken: cancellationToken))
        {
            if (!string.IsNullOrEmpty(update.Text))
            {
                sb.Append(update.Text);
            }
        }

        ChatMessage result = new(ChatRole.Assistant, sb.ToString());
        await context.YieldOutputAsync(result, cancellationToken);
        return result;
    }
}
