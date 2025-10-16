// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using RealtimeKeypoints.Agents;
using RealtimeKeypoints.Executors;
using RealtimeKeypoints.Memory;
using RealtimeKeypoints.Realtime;

namespace RealtimeKeypoints;

public static class Program
{
    public static readonly object ConsoleLock = new();

    public static async Task Main()
    {
        Console.OutputEncoding = Encoding.UTF8;

        string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
            ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        string realtimeDeployment = Environment.GetEnvironmentVariable("AZURE_OPENAI_REALTIME_DEPLOYMENT")
            ?? "gpt-realtime";
        string chatDeployment = Environment.GetEnvironmentVariable("AZURE_OPENAI_CHAT_DEPLOYMENT")
            ?? "gpt-4o-mini";

        using var cancellationSource = new CancellationTokenSource();
        Console.CancelKeyPress += (_, args) =>
        {
            args.Cancel = true;
            if (!cancellationSource.IsCancellationRequested)
            {
                Console.WriteLine();
                Console.WriteLine("Stopping capture...");
                cancellationSource.Cancel();
            }
        };

        try
        {
            await RunAsync(endpoint, realtimeDeployment, chatDeployment, cancellationSource.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            Console.WriteLine("Workflow completed.");
        }
    }

    private static async Task RunAsync(
        string endpoint,
        string realtimeDeployment,
        string chatDeployment,
        CancellationToken cancellationToken)
    {
        var endpointUri = new Uri(endpoint);
        var credential = new AzureCliCredential();

        var memoryStore = new TranscriptMemoryStore(maxEntries: 5000);

        await using var realtimeClient = new AzureRealtimeClient(endpointUri, realtimeDeployment, credential);
        var transcriptionAgent = new RealtimeTranscriptionAgent(realtimeClient);

        var chatClient = new AzureOpenAIClient(endpointUri, credential)
            .GetChatClient(chatDeployment)
            .AsIChatClient();

        var keypointAgent = new RealtimeKeypointAgent(chatClient);
        var keypointThread = (RealtimeKeypointAgent.KeypointThread)keypointAgent.GetNewThread();

        var questionAnswerAgent = new RealtimeQuestionAnswerAgent(chatClient, memoryStore);

        var transcriptionExecutor = new TranscriptionExecutor(transcriptionAgent, memoryStore);
        var keypointProcessorExecutor = new KeypointProcessorExecutor(keypointAgent, memoryStore, keypointThread);
        var questionAnsweringExecutor = new QuestionAnsweringExecutor(questionAnswerAgent, memoryStore);

        Console.WriteLine("🎙️  RealtimeKeypoints Orchestration Started");
        Console.WriteLine("📝 Transcription Agent: ACTIVE (Yellow)");
        Console.WriteLine("💡 Keypoint Agent: ACTIVE (Green)");
        Console.WriteLine("❓ Q&A Agent: ACTIVE (Magenta/Cyan)");
        Console.WriteLine();

        // Run all three executors concurrently
        var stubContext = new StubWorkflowContext();
        var transcriptionTask = transcriptionExecutor.HandleAsync(new object(), stubContext, cancellationToken);
        var keypointTask = keypointProcessorExecutor.HandleAsync(new object(), stubContext, cancellationToken);
        var qaTask = questionAnsweringExecutor.HandleAsync(new object(), stubContext, cancellationToken);

        try
        {
            await Task.WhenAll(transcriptionTask.AsTask(), keypointTask.AsTask(), qaTask.AsTask()).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // Expected when user presses Ctrl+C
        }
    }

    public static void WriteQuestionAnswer(string question, string answer)
    {
        lock (ConsoleLock)
        {
            var previousColor = Console.ForegroundColor;
            Console.ForegroundColor = ConsoleColor.Magenta;
            Console.WriteLine($"\n    ❓ [Question] {question}");
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine($"    💬 [Answer] {answer}");
            Console.ResetColor();
        }
    }

    /// <summary>
    /// Stub implementation of IWorkflowContext for running executors outside of a workflow.
    /// This minimal stub follows Microsoft best practices for test doubles by returning default values.
    /// </summary>
    private sealed class StubWorkflowContext : IWorkflowContext
    {
        public bool ConcurrentRunsEnabled => false;
        public IReadOnlyDictionary<string, string>? TraceContext => null;

        public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default) => default;
        public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default) => default;
        public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default) => default;
        public ValueTask RequestHaltAsync() => default;
        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default) => default;
        public ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default) => new(initialStateFactory());
        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default) => new(new HashSet<string>());
        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default) => default;
        public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default) => default;
    }
}
