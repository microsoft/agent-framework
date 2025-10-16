// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Reflection;
using RealtimeKeypoints.Agents;
using RealtimeKeypoints.Memory;
using RealtimeKeypoints.Realtime;

namespace RealtimeKeypoints.Executors;

/// <summary>
/// Executor that continuously captures audio transcripts and stores them in the memory store.
/// Runs independently and streams transcript segments to memory.
/// </summary>
internal sealed class TranscriptionExecutor : ReflectingExecutor<TranscriptionExecutor>, IMessageHandler<object>
{
    private readonly RealtimeTranscriptionAgent _transcriptionAgent;
    private readonly TranscriptMemoryStore _memoryStore;

    public TranscriptionExecutor(RealtimeTranscriptionAgent transcriptionAgent, TranscriptMemoryStore memoryStore)
        : base("TranscriptionExecutor")
    {
        this._transcriptionAgent = transcriptionAgent ?? throw new ArgumentNullException(nameof(transcriptionAgent));
        this._memoryStore = memoryStore ?? throw new ArgumentNullException(nameof(memoryStore));
    }

    public async ValueTask HandleAsync(object message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        try
        {
            Console.WriteLine("🎙️  Listening for speech. Press Ctrl+C to stop.");

            await foreach (var segment in this._transcriptionAgent.StreamSegmentsAsync(cancellationToken).ConfigureAwait(false))
            {
                if (string.IsNullOrWhiteSpace(segment.Text) || !segment.IsFinal)
                {
                    continue;
                }

                await this._memoryStore.AddAsync(
                    segment.Text,
                    segment.Timestamp,
                    cancellationToken: cancellationToken).ConfigureAwait(false);

                WriteTranscript(segment);

                await context.QueueStateUpdateAsync(
                    "last_transcript_time",
                    segment.Timestamp,
                    scopeName: "TranscriptTracking",
                    cancellationToken: cancellationToken);
            }
        }
        catch (OperationCanceledException)
        {
            Console.WriteLine("Transcription stopped.");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[ERROR Transcription] {ex.Message}");
            throw;
        }
    }

    private static void WriteTranscript(RealtimeTranscriptSegment segment)
    {
        lock (Program.ConsoleLock)
        {
            var previousColor = Console.ForegroundColor;
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine($"[Transcript {segment.Timestamp:HH:mm:ss}] {segment.Text}");
            Console.ForegroundColor = previousColor;
        }
    }
}
