// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace WorkflowMapReduceSample;

/// <summary>
/// Sample: Map-Reduce Word Count with Fan-Out and Fan-In over File-Backed Intermediate Results
///
/// The workflow splits a large text into chunks, maps words to counts in parallel,
/// shuffles intermediate pairs to reducers, then reduces to per-word totals.
/// It also demonstrates workflow visualization for graph visualization.
///
/// Purpose:
/// Show how to:
/// - Partition input once and coordinate parallel mappers with shared state.
/// - Implement map, shuffle, and reduce executors that pass file paths instead of large payloads.
/// - Use fan-out and fan-in edges to express parallelism and joins.
/// - Persist intermediate results to disk to bound memory usage for large inputs.
/// - Visualize the workflow graph using ToDotString and ToMermaidString and export to SVG.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Write access to a temp directory.
/// - A source text file to process.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        Workflow workflow = BuildWorkflow();
        await RunWorkflowAsync(workflow);
    }

    /// <summary>
    /// Builds a map-reduce workflow using a fan-out/fan-in pattern with mappers, reducers, and other executors.
    /// </summary>
    /// <remarks>This method constructs a workflow consisting of multiple stages, including splitting,
    /// mapping, shuffling, reducing, and completion. The workflow is designed to process data in parallel using a
    /// fan-out/fan-in architecture. The resulting workflow is ready for execution and includes all necessary
    /// dependencies between the executors.</remarks>
    /// <returns>A <see cref="Workflow"/> instance representing the constructed workflow.</returns>
    public static Workflow BuildWorkflow()
    {
        // Step 1: Create the mappers and the input splitter
        var mappers = Enumerable.Range(0, 3).Select(i => new Mapper($"map_executor_{i}")).ToArray();
        var splitter = new Split(mappers.Select(m => m.Id).ToArray(), "split_data_executor");

        // Step 2: Create the reducers and the intermidiace shuffler
        var reducers = Enumerable.Range(0, 4).Select(i => new Reducer($"reduce_executor_{i}")).ToArray();
        var shuffler = new Shuffler(reducers.Select(r => r.Id).ToArray(), mappers.Select(m => m.Id).ToArray(), "shuffle_executor");

        // Step 3: Create the output manager
        var completion = new CompletionExecutor("completion_executor");

        // Step 4: Build the concurrent workflow with fan-out/fan-in pattern
        return new WorkflowBuilder(splitter)
            .AddFanOutEdge(splitter, targets: [.. mappers])         // Split -> many mappers
            .AddFanInEdge(shuffler, sources: [.. mappers])          // All mappers -> shuffle
            .AddFanOutEdge(shuffler, targets: [.. reducers])        // Shuffle -> many reducers
            .AddFanInEdge(completion, sources: [.. reducers])       // All reducers -> completion
            .WithOutputFrom(completion)
            .Build();
    }

    /// <summary>
    /// Executes the specified workflow asynchronously using a predefined input text and processes its output events.
    /// </summary>
    /// <remarks>This method reads input text from a file located in the "resources" directory. If the file is
    /// not found,  a default sample text is used. The workflow is executed with the input text, and its events are
    /// streamed  and processed in real-time. If the workflow produces output files, their paths and contents are
    /// displayed.</remarks>
    /// <param name="workflow">The workflow to execute. This defines the sequence of operations to be performed.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    private static async Task RunWorkflowAsync(Workflow workflow)
    {
        // Step 1: Read the input text
        var resourcesPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "..", "..", "..", "resources");
        var textFilePath = Path.Combine(resourcesPath, "long_text.txt");

        string rawText;
        if (File.Exists(textFilePath))
        {
            rawText = await File.ReadAllTextAsync(textFilePath);
        }
        else
        {
            // Use sample text if file doesn't exist
            Console.WriteLine($"Note: {textFilePath} not found, using sample text");
            rawText = "The quick brown fox jumps over the lazy dog. The dog was very lazy. The fox was very quick.";
        }

        // Step 2: Run the workflow
        Console.WriteLine("\n=== RUNNING WORKFLOW ===\n");
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, rawText);
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            Console.WriteLine($"Event: {evt}");
            if (evt is WorkflowOutputEvent outputEvent)
            {
                Console.WriteLine("\nFinal Output Files:");
                if (outputEvent.Data is List<string> filePaths)
                {
                    foreach (var filePath in filePaths)
                    {
                        Console.WriteLine($"  - {filePath}");
                        if (File.Exists(filePath))
                        {
                            var content = await File.ReadAllTextAsync(filePath);
                            Console.WriteLine($"    Contents:\n{content}");
                        }
                    }
                }
            }
        }
    }
}

#region Executors

/// <summary>
/// Splits data into roughly equal chunks based on the number of mapper nodes.
/// </summary>
internal sealed class Split(string[] mapperIds, string id) :
    Executor<string>(id)
{
    private readonly string[] _mapperIds = mapperIds;
    private static readonly string[] s_lineSeparators = ["\r\n", "\r", "\n"];

    /// <summary>
    /// Tokenize input and assign contiguous index ranges to each mapper via shared state.
    /// </summary>
    public override async ValueTask HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Ensure temp directory exists
        Directory.CreateDirectory(MapReduceConstants.TempDir);

        // Process the data into a list of words and remove any empty lines
        var wordList = Preprocess(message);

        // Store the tokenized words once so that all mappers can read by index
        await context.QueueStateUpdateAsync(MapReduceConstants.DataToProcessKey, wordList, scopeName: MapReduceConstants.StateScope, cancellationToken);

        // Divide indices into contiguous slices for each mapper
        var mapperCount = this._mapperIds.Length;
        var chunkSize = wordList.Length / mapperCount;

        async Task ProcessChunkAsync(int i)
        {
            // Determine the start and end indices for this mapper's chunk
            var startIndex = i * chunkSize;
            var endIndex = i < mapperCount - 1 ? startIndex + chunkSize : wordList.Length;

            // Save the indices under the mapper's Id
            await context.QueueStateUpdateAsync(this._mapperIds[i], (startIndex, endIndex), scopeName: MapReduceConstants.StateScope, cancellationToken);

            // Notify the mapper that data is ready
            await context.SendMessageAsync(new SplitComplete(), targetId: this._mapperIds[i], cancellationToken);
        }

        // Process all the chunks
        var tasks = Enumerable.Range(0, mapperCount).Select(ProcessChunkAsync);
        await Task.WhenAll(tasks);
    }

    private static string[] Preprocess(string data)
    {
        var lines = data.Split(s_lineSeparators, StringSplitOptions.RemoveEmptyEntries)
            .Select(line => line.Trim())
            .Where(line => !string.IsNullOrWhiteSpace(line));

        return lines
            .SelectMany(line => line.Split(' ', StringSplitOptions.RemoveEmptyEntries))
            .Where(word => !string.IsNullOrWhiteSpace(word))
            .ToArray();
    }
}

/// <summary>
/// Maps each token to a count of 1 and writes pairs to a per-mapper file.
/// </summary>
internal sealed class Mapper(string id) : Executor<SplitComplete>(id)
{
    /// <summary>
    /// Read the assigned slice, emit (word, 1) pairs, and persist to disk.
    /// </summary>
    public override async ValueTask HandleAsync(SplitComplete message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        var dataToProcess = await context.ReadStateAsync<string[]>(MapReduceConstants.DataToProcessKey, scopeName: MapReduceConstants.StateScope, cancellationToken);
        var chunk = await context.ReadStateAsync<(int start, int end)>(this.Id, scopeName: MapReduceConstants.StateScope, cancellationToken);

        var results = dataToProcess![chunk.start..chunk.end]
            .Select(word => (word, 1))
            .ToArray();

        // Write this mapper's results as simple text lines for easy debugging
        var filePath = Path.Combine(MapReduceConstants.TempDir, $"map_results_{this.Id}.txt");
        var lines = results.Select(r => $"{r.word}: {r.Item2}");
        await File.WriteAllLinesAsync(filePath, lines, cancellationToken);

        await context.SendMessageAsync(new MapComplete(filePath), cancellationToken: cancellationToken);
    }
}

/// <summary>
/// Groups intermediate pairs by key and partitions them across reducers.
/// </summary>
internal sealed class Shuffler(string[] reducerIds, string[] mapperIds, string id) :
    Executor<MapComplete>(id)
{
    private readonly string[] _reducerIds = reducerIds;
    private readonly string[] _mapperIds = mapperIds;
    private readonly List<MapComplete> _mapResults = [];

    /// <summary>
    /// Aggregate mapper outputs and write one partition file per reducer.
    /// </summary>
    public override async ValueTask HandleAsync(MapComplete message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._mapResults.Add(message);

        // Wait for all mappers to complete
        if (this._mapResults.Count < this._mapperIds.Length)
        {
            return;
        }

        var chunks = await this.PreprocessAsync(this._mapResults);

        async Task ProcessChunkAsync(List<(string key, List<int> values)> chunk, int index)
        {
            // Write one grouped partition for reducer index and notify that reducer
            var filePath = Path.Combine(MapReduceConstants.TempDir, $"shuffle_results_{index}.txt");
            var lines = chunk.Select(kvp => $"{kvp.key}: {JsonSerializer.Serialize(kvp.values)}");
            await File.WriteAllLinesAsync(filePath, lines, cancellationToken);

            await context.SendMessageAsync(new ShuffleComplete(filePath, this._reducerIds[index]), cancellationToken: cancellationToken);
        }

        var tasks = chunks.Select((chunk, i) => ProcessChunkAsync(chunk, i));
        await Task.WhenAll(tasks);
    }

    /// <summary>
    /// Load all mapper files, group by key, sort keys, and partition for reducers.
    /// </summary>
    private async Task<List<List<(string key, List<int> values)>>> PreprocessAsync(List<MapComplete> data)
    {
        // Load all intermediate pairs
        var mapResults = new List<(string key, int value)>();
        foreach (var result in data)
        {
            var lines = await File.ReadAllLinesAsync(result.FilePath);
            foreach (var line in lines)
            {
                var parts = line.Split(": ");
                if (parts.Length == 2)
                {
                    mapResults.Add((parts[0], int.Parse(parts[1])));
                }
            }
        }

        // Group values by token
        var intermediateResults = mapResults
            .GroupBy(r => r.key)
            .ToDictionary(g => g.Key, g => g.Select(r => r.value).ToList());

        // Deterministic ordering helps with debugging and test stability
        var aggregatedResults = intermediateResults
            .Select(kvp => (key: kvp.Key, values: kvp.Value))
            .OrderBy(x => x.key)
            .ToList();

        // Partition keys across reducers as evenly as possible
        var reduceExecutorCount = this._reducerIds.Length; // Use actual number of reducers
        if (reduceExecutorCount == 0)
        {
            reduceExecutorCount = 1;
        }

        var chunkSize = aggregatedResults.Count / reduceExecutorCount;
        var remaining = aggregatedResults.Count % reduceExecutorCount;

        var chunks = new List<List<(string key, List<int> values)>>();
        for (int i = 0; i < aggregatedResults.Count - remaining; i += chunkSize)
        {
            chunks.Add(aggregatedResults.GetRange(i, chunkSize));
        }

        if (remaining > 0 && chunks.Count > 0)
        {
            chunks[^1].AddRange(aggregatedResults.TakeLast(remaining));
        }
        else if (chunks.Count == 0)
        {
            chunks.Add(aggregatedResults);
        }

        return chunks;
    }
}

/// <summary>
/// Sums grouped counts per key for its assigned partition.
/// </summary>
internal sealed class Reducer(string id) : Executor<ShuffleComplete>(id)
{
    /// <summary>
    /// Read one shuffle partition and reduce it to totals.
    /// </summary>
    public override async ValueTask HandleAsync(ShuffleComplete message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (message.ReducerId != this.Id)
        {
            // This partition belongs to a different reducer. Skip.
            return;
        }

        // Read grouped values from the shuffle output
        var lines = await File.ReadAllLinesAsync(message.FilePath, cancellationToken);

        // Sum values per key. Values are serialized JSON arrays like [1, 1, ...]
        var reducedResults = new Dictionary<string, int>();
        foreach (var line in lines)
        {
            var parts = line.Split(": ", 2);
            if (parts.Length == 2)
            {
                var key = parts[0];
                var values = JsonSerializer.Deserialize<List<int>>(parts[1]);
                reducedResults[key] = values?.Sum() ?? 0;
            }
        }

        // Persist our partition totals
        var filePath = Path.Combine(MapReduceConstants.TempDir, $"reduced_results_{this.Id}.txt");
        var outputLines = reducedResults.Select(kvp => $"{kvp.Key}: {kvp.Value}");
        await File.WriteAllLinesAsync(filePath, outputLines, cancellationToken);

        await context.SendMessageAsync(new ReduceComplete(filePath), cancellationToken: cancellationToken);
    }
}

/// <summary>
/// Joins all reducer outputs and yields the final output.
/// </summary>
internal sealed class CompletionExecutor(string id) :
    Executor<List<ReduceComplete>>(id)
{
    /// <summary>
    /// Collect reducer output file paths and yield final output.
    /// </summary>
    public override async ValueTask HandleAsync(List<ReduceComplete> message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        var filePaths = message.ConvertAll(r => r.FilePath);
        await context.YieldOutputAsync(filePaths, cancellationToken);
    }
}

#endregion

#region Events

/// <summary>
/// Marker event published when splitting finishes. Triggers map executors.
/// </summary>
internal sealed class SplitComplete : WorkflowEvent;

/// <summary>
/// Signal that a mapper wrote its intermediate pairs to file.
/// </summary>
internal sealed class MapComplete(string FilePath) : WorkflowEvent
{
    public string FilePath { get; } = FilePath;
}

/// <summary>
/// Signal that a shuffle partition file is ready for a specific reducer.
/// </summary>
internal sealed class ShuffleComplete(string FilePath, string ReducerId) : WorkflowEvent
{
    public string FilePath { get; } = FilePath;
    public string ReducerId { get; } = ReducerId;
}

/// <summary>
/// Signal that a reducer wrote final counts for its partition.
/// </summary>
internal sealed class ReduceComplete(string FilePath) : WorkflowEvent
{
    public string FilePath { get; } = FilePath;
}

#endregion

#region Helpers

/// <summary>
/// Provides constant values used in the MapReduce workflow.
/// </summary>
/// <remarks>This class contains keys and paths that are utilized throughout the MapReduce process, including
/// identifiers for data processing and temporary storage locations.</remarks>
internal static class MapReduceConstants
{
    public static string DataToProcessKey = "data_to_be_processed";
    public static string TempDir = Path.Combine(Path.GetTempPath(), "workflow_viz_sample");
    public static string StateScope = "MapReduceState";
}

#endregion
