// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;

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
        // Create the mapper executors
        const int NumberOfMappers = 3;
        var mapperIds = Enumerable.Range(0, NumberOfMappers).Select(i => $"mapper_{i}");
        var mappers = mapperIds.Select(id => new Mapper(id));

        // Create the data spitter executor
        var splitter = new Split(mapperIds.ToArray());

        // Create the 

        // Build the concurrent workflow with fan-out/fan-in pattern
        var workflow = new WorkflowBuilder(splitter)
            .AddFanOutEdge(splitter, targets: [.. mappers])
            .AddFanInEdge(aggregator, sources: [.. mappers])
            .Build();

        // Generate and display workflow visualization
        Console.WriteLine("=== WORKFLOW VISUALIZATION ===");

        // Display DOT (GraphViz) representation
        Console.WriteLine("\n--- GraphViz DOT Format ---");
        var dotString = workflow.ToDotString();
        Console.WriteLine(dotString);

        // Display Mermaid representation
        Console.WriteLine("\n--- Mermaid Format ---");
        var mermaid = workflow.ToMermaidString();
        Console.WriteLine(mermaid);
    }
}

internal sealed class SplitComplete : WorkflowEvent
{
}

internal sealed class MapComplete(string JobId, string MapperId) : WorkflowEvent()
{
    public string MapperId { get; } = MapperId;

    public string JobId { get; } = JobId;
}

internal static class Constants
{
    public static string DataToProcessKey = "data_to_be_processed";
}

internal sealed class Split(string[] mapperIds) :
    ReflectingExecutor<Split>("Split"),
    IMessageHandler<string>
{
    private readonly string[] _mapperIds = mapperIds;
    internal static readonly string[] lineSeparators = ["\r\n", "\r", "\n"];

    /// <summary>
    /// Handles the processing of a message by dividing it into chunks and notifying mappers for further processing.
    /// </summary>
    /// <remarks>This method processes the input message into a list of words, stores the processed data in
    /// the workflow state,  and divides the data into chunks for each mapper. Each mapper is notified when its chunk is
    /// ready for processing.</remarks>
    /// <param name="message">The input message to be processed. Cannot be null or empty.</param>
    /// <param name="context">The workflow context used for state updates and message communication. Cannot be null.</param>
    /// <returns>A <see cref="ValueTask"/> that represents the asynchronous operation.</returns>
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        // Process the data into a list of words and remove any empty lines
        var wordList = this.Preprocess(message);

        // Store the tokenized words once so that all mappers can read by index
        await context.QueueStateUpdateAsync(Constants.DataToProcessKey, wordList);

        // Divide indices into contiguous slices for each mapper
        var mapperCount = this._mapperIds.Length;
        var chunkSize = wordList.Length / mapperCount;

        async Task ProcessChunkAsync(int i)
        {
            // Determine the start and end indices for this mapper's chunk
            var startIndex = i * chunkSize;
            var endIndex = i < mapperCount - 1 ? startIndex + chunkSize : wordList.Length;

            // Save the indices under the mappers Id
            await context.QueueStateUpdateAsync(this._mapperIds[i], (startIndex, endIndex));

            // Notify the mapper that data is ready
            await context.SendMessageAsync(new SplitComplete(), targetId: this._mapperIds[i]);
        }

        // Process all the chunks
        var tasks = Enumerable.Range(0, mapperCount).Select(i => ProcessChunkAsync(i));
        await Task.WhenAll(tasks);
    }

    private string[] Preprocess(string data)
    {
        var lines = data.Split(lineSeparators, StringSplitOptions.RemoveEmptyEntries);
        return lines.SelectMany(line => line.Split(' ')).ToArray();
    }
}

internal sealed class Mapper(string id) : ReflectingExecutor<Mapper>(id), IMessageHandler<SplitComplete>
{
    public async ValueTask HandleAsync(SplitComplete message, IWorkflowContext context)
    {
        var dataToProcess = await context.ReadStateAsync<string[]>(Constants.DataToProcessKey);
        (int start, int stop) chunk = await context.ReadStateAsync<(int, int)>(this.Id);

        var mapped = dataToProcess?[chunk.start..chunk.stop].Select(data => (dataToProcess, 1));

        var jobId = $"mapped_{this.Id}";
        await context.QueueStateUpdateAsync(jobId, mapped);
        await context.SendMessageAsync(new MapComplete(jobId, this.Id));
    }
}

internal sealed class Shuffle : ReflectingExecutor<Shuffle>, IMessageHandler<MapComplete>
{
    private readonly string[] _mapperIds;
    private readonly string[] _reducerIds;
    private readonly HashSet<string> _outstandingMappers;
    private readonly 

    public Shuffle(string[] mapperIds, string[] reducerIds) : base("shuffle")
    {
        this._mapperIds = mapperIds;
        this._reducerIds = reducerIds;
        this._outstandingMappers = [.. reducerIds];
    }

    public async ValueTask HandleAsync(MapComplete message, IWorkflowContext context)
    {
        // Read the mapped data from state
        await context.ReadStateAsync<(string, int)[]>(message.JobId);

        async Task ProcessChunk()
        {

        }
    }

    private async Task PreprocessAsync(MapComplete message, IWorkflowContext context)
    {
        // Read the mapped chunk in from state
        var mappedChunk = await context.ReadStateAsync<(string, int)[]>(message.JobId);
        var sortedChunk = mappedChunk?.GroupBy(item => item.Item1);
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
            await context.YieldOutputAsync(consolidatedReport);
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
