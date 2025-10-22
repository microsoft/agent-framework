// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Reflection;
using Microsoft.Extensions.AI;
using RealtimeKeypoints.Agents;
using RealtimeKeypoints.Memory;

namespace RealtimeKeypoints.Executors;

/// <summary>
/// Executor that runs in a continuous loop, polling the memory store for new transcripts.
/// When new transcripts are found, it extracts keypoints and displays them.
/// </summary>
internal sealed class KeypointProcessorExecutor : ReflectingExecutor<KeypointProcessorExecutor>, IMessageHandler<object>
{
    private readonly RealtimeKeypointAgent _keypointAgent;
    private readonly TranscriptMemoryStore _memoryStore;
    private readonly RealtimeKeypointAgent.KeypointThread _keypointThread;

    public KeypointProcessorExecutor(
        RealtimeKeypointAgent keypointAgent,
        TranscriptMemoryStore memoryStore,
        RealtimeKeypointAgent.KeypointThread? keypointThread = null)
        : base("KeypointProcessorExecutor")
    {
        this._keypointAgent = keypointAgent ?? throw new ArgumentNullException(nameof(keypointAgent));
        this._memoryStore = memoryStore ?? throw new ArgumentNullException(nameof(memoryStore));
        this._keypointThread = keypointThread ?? (RealtimeKeypointAgent.KeypointThread)keypointAgent.GetNewThread();
    }

    public async ValueTask HandleAsync(object message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        try
        {
            Console.WriteLine("💡 Keypoint Agent: ACTIVE");
            DateTimeOffset lastProcessedTime = DateTimeOffset.MinValue;
            const int PollingIntervalMs = 3000;

            while (!cancellationToken.IsCancellationRequested)
            {
                try
                {
                    await Task.Delay(PollingIntervalMs, cancellationToken).ConfigureAwait(false);

                    var recentTranscripts = await this._memoryStore.GetRecentTranscriptsAsync(
                        TimeSpan.FromSeconds(60),
                        cancellationToken).ConfigureAwait(false);

                    if (recentTranscripts.Count == 0)
                    {
                        continue;
                    }

                    var newTranscripts = new List<string>();
                    foreach (var transcript in recentTranscripts)
                    {
                        var timestamp = await this._memoryStore.GetTranscriptTimestampAsync(
                            transcript,
                            cancellationToken).ConfigureAwait(false);
                        if (timestamp > lastProcessedTime)
                        {
                            newTranscripts.Add(transcript);
                        }
                    }

                    if (newTranscripts.Count == 0)
                    {
                        continue;
                    }

                    lastProcessedTime = await this._memoryStore.GetTranscriptTimestampAsync(
                        recentTranscripts.Last(),
                        cancellationToken).ConfigureAwait(false);

                    string combinedText = string.Join(" ", newTranscripts);

                    var response = await this._keypointAgent.RunAsync(
                        new[] { new ChatMessage(ChatRole.User, combinedText) },
                        this._keypointThread,
                        options: null,
                        cancellationToken: cancellationToken).ConfigureAwait(false);

                    foreach (var responseMessage in response.Messages)
                    {
                        if (string.IsNullOrWhiteSpace(responseMessage.Text))
                        {
                            continue;
                        }

                        WriteKeyPoint(responseMessage.Text, responseMessage.CreatedAt);
                    }
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[ERROR Keypoint] {ex.Message}");
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[ERROR Keypoint Processor] {ex.Message}");
            throw;
        }
    }

    private static void WriteKeyPoint(string keyPoint, DateTimeOffset? createdAt)
    {
        lock (Program.ConsoleLock)
        {
            var previousColor = Console.ForegroundColor;
            Console.ForegroundColor = ConsoleColor.Green;
            var timestamp = createdAt ?? DateTimeOffset.UtcNow;
            Console.WriteLine($"    💡 [Key Point {timestamp:HH:mm:ss}] {keyPoint}");
            Console.ForegroundColor = previousColor;
        }
    }
}
