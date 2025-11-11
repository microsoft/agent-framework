// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WriterCriticWorkflow;

/// <summary>
/// This sample demonstrates an iterative refinement workflow between Writer and Critic agents.
///
/// The workflow implements a content creation and review loop that:
/// 1. Writer creates initial content based on the user's request
/// 2. Critic reviews the content and provides feedback using structured output
/// 3. If approved: Summary executor presents the final content
/// 4. If rejected: Writer revises based on feedback (loops back)
/// 5. Continues until approval or max iterations (3) is reached
///
/// This pattern is useful when you need:
/// - Iterative content improvement through feedback loops
/// - Quality gates with reviewer approval
/// - Maximum iteration limits to prevent infinite loops
/// - Conditional workflow routing based on agent decisions
/// - Structured output for reliable decision-making
///
/// Key Learning: Workflows can implement loops with conditional edges, shared state,
/// and structured output for robust agent decision-making.
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
        string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        IChatClient chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

        // Create executors for content creation and review
        WriterExecutor writer = new(chatClient);
        CriticExecutor critic = new(chatClient);
        SummaryExecutor summary = new(chatClient);

        // Build the workflow with conditional routing based on critic's decision
        WorkflowBuilder workflowBuilder = new WorkflowBuilder(writer)
            .AddEdge(writer, critic)
            .AddSwitch(critic, sw => sw
                .AddCase<CriticDecision>(cd => cd?.Approved == true, summary)
                .AddCase<CriticDecision>(cd => cd?.Approved == false, writer))
            .WithOutputFrom(summary);

        // Execute the workflow with a sample task
        // The workflow loops back to Writer if content is rejected,
        // or proceeds to Summary if approved. State tracking ensures we don't loop forever.
        Console.WriteLine(new string('=', 80));
        Console.WriteLine("TASK: Write a short blog post about AI ethics (200 words)");
        Console.WriteLine(new string('=', 80) + "\n");

        const string InitialTask = "Write a 200-word blog post about AI ethics. Make it thoughtful and engaging.";

        Workflow workflow = workflowBuilder.Build();
        await ExecuteWorkflowAsync(workflow, InitialTask);

        Console.WriteLine("\n✅ Sample Complete: Writer-Critic iteration demonstrates conditional workflow loops\n");
        Console.WriteLine("Key Concepts Demonstrated:");
        Console.WriteLine("  ✓ Iterative refinement loop with conditional routing");
        Console.WriteLine("  ✓ Shared workflow state for iteration tracking");
        Console.WriteLine($"  ✓ Max iteration cap ({MaxIterations}) for safety");
        Console.WriteLine("  ✓ Multiple message handlers in a single executor");
        Console.WriteLine("  ✓ Streaming support with structured output\n");
    }

    private static async Task ExecuteWorkflowAsync(Workflow workflow, string input)
    {
        // Execute in streaming mode to see real-time progress
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, input);

        // Watch the workflow events
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            switch (evt)
            {
                case AgentRunUpdateEvent agentUpdate:
                    // Stream agent output in real-time
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
/// Structured output schema for the Critic's decision.
/// Uses JsonPropertyName and Description attributes for OpenAI's JSON schema.
/// </summary>
[Description("Critic's review decision including approval status and feedback")]
[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via JSON deserialization")]
internal sealed class CriticDecision
{
    [JsonPropertyName("approved")]
    [Description("Whether the content is approved (true) or needs revision (false)")]
    public bool Approved { get; set; }

    [JsonPropertyName("feedback")]
    [Description("Specific feedback for improvements if not approved, empty if approved")]
    public string Feedback { get; set; } = "";

    // Non-JSON properties for workflow use
    [JsonIgnore]
    public string Content { get; set; } = "";

    [JsonIgnore]
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
/// Uses structured output with streaming for reliable decision-making.
/// </summary>
internal sealed class CriticExecutor : Executor<ChatMessage, CriticDecision>
{
    private readonly AIAgent _agent;

    public CriticExecutor(IChatClient chatClient) : base("Critic")
    {
        this._agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions
        {
            Name = "Critic",
            Instructions = """
                You are a constructive critic. Review the content and provide specific feedback.
                Always try to provide actionable suggestions for improvement and strive to identify improvement points.
                Only approve if the content is high quality, clear, and meets the original requirements and you see no improvement points.
                
                Provide your decision as structured output with:
                - approved: true if content is good, false if revisions needed
                - feedback: specific improvements needed (empty if approved)
                
                Be concise but specific in your feedback.
                """,
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema<CriticDecision>()
            }
        });
    }

    public override async ValueTask<CriticDecision> HandleAsync(
        ChatMessage message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        FlowState state = await FlowStateHelpers.ReadFlowStateAsync(context);

        Console.WriteLine($"=== Critic (Iteration {state.Iteration}) ===\n");

        // Use RunStreamingAsync to get streaming updates, then deserialize at the end
        IAsyncEnumerable<AgentRunResponseUpdate> updates = this._agent.RunStreamingAsync(message, cancellationToken: cancellationToken);

        // Stream the output in real-time (for any rationale/explanation)
        await foreach (AgentRunResponseUpdate update in updates)
        {
            if (!string.IsNullOrEmpty(update.Text))
            {
                Console.Write(update.Text);
            }
        }
        Console.WriteLine("\n");

        // Convert the stream to a response and deserialize the structured output
        AgentRunResponse response = await updates.ToAgentRunResponseAsync(cancellationToken);
        CriticDecision decision = response.Deserialize<CriticDecision>(JsonSerializerOptions.Web);

        Console.WriteLine($"Decision: {(decision.Approved ? "✅ APPROVED" : "❌ NEEDS REVISION")}");
        if (!string.IsNullOrEmpty(decision.Feedback))
        {
            Console.WriteLine($"Feedback: {decision.Feedback}");
        }
        Console.WriteLine();

        // Safety: approve if max iterations reached
        if (!decision.Approved && state.Iteration >= Program.MaxIterations)
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine($"⚠️ Max iterations ({Program.MaxIterations}) reached - auto-approving");
            Console.ResetColor();
            decision.Approved = true;
            decision.Feedback = "";
        }

        // Increment iteration ONLY if rejecting (will loop back to Writer)
        if (!decision.Approved)
        {
            state.Iteration++;
        }

        // Store the decision in history
        state.History.Add(new ChatMessage(ChatRole.Assistant,
            $"[Decision: {(decision.Approved ? "Approved" : "Needs Revision")}] {decision.Feedback}"));
        await FlowStateHelpers.SaveFlowStateAsync(context, state);

        // Populate workflow-specific fields
        decision.Content = message.Text ?? "";
        decision.Iteration = state.Iteration;

        return decision;
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
