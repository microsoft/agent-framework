// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace ConcurrentWithVisualizationSample;

/// <summary>
/// This sample demonstrates concurrent execution using "fan-out" and "fan-in" patterns
/// with workflow visualization using the WorkflowViz class.
///
/// The workflow structure:
/// 1. DispatchExecutor sends the same prompt to multiple domain experts concurrently (fan-out)
/// 2. Research, Marketing, and Legal agents analyze the prompt independently and in parallel
/// 3. AggregationExecutor collects all responses and combines them into a consolidated report (fan-in)
/// 4. WorkflowViz generates visual representations of the workflow structure
///
/// This pattern is useful for getting multiple expert perspectives on business decisions,
/// product launches, or strategic planning where you need diverse domain expertise.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - An Azure OpenAI chat completion deployment must be configured.
/// - Set AZURE_OPENAI_ENDPOINT and optionally AZURE_OPENAI_DEPLOYMENT_NAME environment variables.
/// - For SVG/PNG/PDF export: Install Graphviz (https://graphviz.org/download/)
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ??
            throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
            .GetChatClient(deploymentName).AsIChatClient();

        // Create domain expert agents
        ChatClientAgent researcher = new(
            chatClient,
            name: "Researcher",
            instructions: "You are an expert market and product researcher. Given a prompt, provide concise, " +
                         "factual insights, opportunities, and risks. Focus on data-driven analysis."
        );

        ChatClientAgent marketer = new(
            chatClient,
            name: "Marketer",
            instructions: "You are a creative marketing strategist. Craft compelling value propositions and " +
                         "target messaging aligned to the prompt. Focus on customer appeal and market positioning."
        );

        ChatClientAgent legal = new(
            chatClient,
            name: "Legal",
            instructions: "You are a cautious legal and compliance reviewer. Highlight constraints, disclaimers, " +
                         "and policy concerns based on the prompt. Focus on risk mitigation and regulatory compliance."
        );

        // Create workflow orchestration executors
        var dispatcher = new DispatchToExpertsExecutor(["Researcher", "Marketer", "Legal"]);
        var aggregator = new AggregateInsightsExecutor(["Researcher", "Marketer", "Legal"]);

        // Build the concurrent workflow with fan-out/fan-in pattern
        var workflow = new WorkflowBuilder(dispatcher)
            .AddFanOutEdge(dispatcher, targets: [researcher, marketer, legal])
            .AddFanInEdge(aggregator, sources: [researcher, marketer, legal])
            .Build<string>();

        // Generate and display workflow visualization
        Console.WriteLine("=== WORKFLOW VISUALIZATION ===");
        var viz = new WorkflowViz(workflow);

        // Display DOT (GraphViz) representation
        Console.WriteLine("\n--- GraphViz DOT Format ---");
        var dotString = viz.ToDotString();
        Console.WriteLine(dotString);

        // Try to export visualizations to files
        Console.WriteLine("\n--- Exporting Visualizations ---");
        try
        {
            // Export DOT file (always works)
            var dotFile = await viz.ExportAsync("dot", "workflow.dot");
            Console.WriteLine($"DOT file saved to: {dotFile}");

            try
            {
                // Try to export SVG (requires Graphviz installation)
                var svgFile = await viz.ExportAsync("svg", "workflow.svg");
                Console.WriteLine($"SVG file saved to: {svgFile}");
            }
            catch (InvalidOperationException ex) when (ex.Message.Contains("Graphviz"))
            {
                Console.WriteLine("SVG export requires Graphviz installation. Download from: https://graphviz.org/download/");
            }

            try
            {
                // Try to export PNG (requires Graphviz installation)
                var pngFile = await viz.ExportAsync("png", "workflow.png");
                Console.WriteLine($"PNG file saved to: {pngFile}");
            }
            catch (InvalidOperationException ex) when (ex.Message.Contains("Graphviz"))
            {
                Console.WriteLine("PNG export requires Graphviz installation.");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Visualization export failed: {ex.Message}");
        }

        // Execute the workflow
        Console.WriteLine("\n=== WORKFLOW EXECUTION ===");
        const string Prompt = "We are launching a new budget-friendly electric bike for urban commuters.";
        Console.WriteLine($"Input prompt: {Prompt}");
        Console.WriteLine("\nExecuting concurrent analysis by domain experts...\n");

        StreamingRun run = await InProcessExecution.StreamAsync(workflow, Prompt);
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is WorkflowCompletedEvent completed)
            {
                Console.WriteLine("=== CONSOLIDATED EXPERT ANALYSIS ===");
                Console.WriteLine(completed.Data);
            }
        }

        Console.WriteLine("\n=== WORKFLOW COMPLETED ===");
        Console.WriteLine("Check the generated visualization files in the current directory:");
        Console.WriteLine("- workflow.dot (GraphViz source)");
        Console.WriteLine("- workflow.svg (if Graphviz is installed)");
        Console.WriteLine("- workflow.png (if Graphviz is installed)");
    }
}

/// <summary>
/// Executor that dispatches the incoming prompt to all expert agent executors (fan-out).
/// </summary>
internal sealed class DispatchToExpertsExecutor(string[] expertIds) :
    ReflectingExecutor<DispatchToExpertsExecutor>("DispatchToExperts"),
    IMessageHandler<string>
{
    private readonly string[] _expertIds = expertIds;

    /// <summary>
    /// Dispatches the user prompt to all domain expert agents concurrently.
    /// </summary>
    /// <param name="message">The user prompt to analyze</param>
    /// <param name="context">Workflow context for message passing</param>
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        Console.WriteLine($"Dispatching prompt to {this._expertIds.Length} domain experts...");

        // Send the prompt as a user message to all expert agents
        await context.SendMessageAsync(new ChatMessage(ChatRole.User, message));

        // Send turn tokens to start processing
        await context.SendMessageAsync(new TurnToken(emitEvents: true));
    }
}

/// <summary>
/// Structured data class for aggregated expert insights.
/// </summary>
public class AggregatedInsights
{
    public string Research { get; }
    public string Marketing { get; }
    public string Legal { get; }

    public AggregatedInsights(string research, string marketing, string legal)
    {
        this.Research = research;
        this.Marketing = marketing;
        this.Legal = legal;
    }
}

/// <summary>
/// Executor that aggregates expert agent responses into a consolidated result (fan-in).
/// </summary>
internal sealed class AggregateInsightsExecutor(string[] expertIds) :
    ReflectingExecutor<AggregateInsightsExecutor>("AggregateInsights"),
    IMessageHandler<ChatMessage>
{
    private readonly string[] _expertIds = expertIds;
    private readonly Dictionary<string, string> _responsesByExpert = new();

    /// <summary>
    /// Collects responses from expert agents and aggregates them when all have responded.
    /// </summary>
    /// <param name="message">Response message from an expert agent</param>
    /// <param name="context">Workflow context for emitting completion events</param>
    public async ValueTask HandleAsync(ChatMessage message, IWorkflowContext context)
    {
        var expertName = message.AuthorName ?? "Unknown";
        this._responsesByExpert[expertName] = message.Text ?? "";

        Console.WriteLine($"Received response from {expertName}");

        // Check if we have responses from all expected experts
        if (this._responsesByExpert.Count == this._expertIds.Length)
        {
            Console.WriteLine("All expert responses received. Aggregating insights...");

            // Extract responses by domain
            var research = this._responsesByExpert.TryGetValue("Researcher", out var researchText) ? researchText : "No research analysis provided.";
            var marketing = this._responsesByExpert.TryGetValue("Marketer", out var marketingText) ? marketingText : "No marketing analysis provided.";
            var legal = this._responsesByExpert.TryGetValue("Legal", out var legalText) ? legalText : "No legal analysis provided.";

            // Create structured insights
            var insights = new AggregatedInsights(research, marketing, legal);

            // Format consolidated report
            var consolidatedReport = FormatConsolidatedReport(insights);

            // Complete the workflow with the aggregated result
            await context.AddEventAsync(new WorkflowCompletedEvent(consolidatedReport));
        }
    }

    private static string FormatConsolidatedReport(AggregatedInsights insights)
    {
        return $"""
               CONSOLIDATED EXPERT ANALYSIS
               ============================

               RESEARCH FINDINGS
               {insights.Research}

               MARKETING PERSPECTIVE
               {insights.Marketing}

               LEGAL & COMPLIANCE REVIEW
               {insights.Legal}

               ============================
               Analysis complete. All domain expertise consolidated.
               """;
    }
}
