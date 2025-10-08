// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Azure;
using Azure.AI.OpenAI;
using Microsoft.Extensions.AI;
using Microsoft.Agents.AI;
using RealtimeKeypoints.Agents;
using RealtimeKeypoints.Realtime;
using RealtimeKeypoints.Memory;

namespace RealtimeKeypoints;

public static class Program
{
    public static async Task Main()
    {
        Console.OutputEncoding = Encoding.UTF8;

        string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
            ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        string realtimeDeployment = Environment.GetEnvironmentVariable("AZURE_OPENAI_REALTIME_DEPLOYMENT")
            ?? throw new InvalidOperationException("AZURE_OPENAI_REALTIME_DEPLOYMENT is not set.");
        string chatDeployment = Environment.GetEnvironmentVariable("AZURE_OPENAI_CHAT_DEPLOYMENT")
            ?? realtimeDeployment;
        string apiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY")
            ?? throw new InvalidOperationException("AZURE_OPENAI_API_KEY is not set.");

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
            await RunAsync(endpoint, realtimeDeployment, chatDeployment, apiKey, cancellationSource.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // Graceful shutdown.
        }
    }

    private static async Task RunAsync(string endpoint, string realtimeDeployment, string chatDeployment, string apiKey, CancellationToken cancellationToken)
    {
        var endpointUri = new Uri(endpoint);

        // Create memory store for transcript persistence
        var memoryStore = new TranscriptMemoryStore(maxEntries: 1000);

        // Create separate channels for each consumer to avoid competition
        var displayChannel = Channel.CreateUnbounded<RealtimeTranscriptSegment>(new UnboundedChannelOptions
        {
            SingleReader = true,
            SingleWriter = true
        });

        var keypointChannel = Channel.CreateUnbounded<RealtimeTranscriptSegment>(new UnboundedChannelOptions
        {
            SingleReader = true,
            SingleWriter = true
        });

        await using var realtimeClient = new AzureRealtimeClient(endpointUri, realtimeDeployment, apiKey);
        var transcriptionAgent = new RealtimeTranscriptionAgent(realtimeClient);

        var chatClient = new AzureOpenAIClient(endpointUri, new AzureKeyCredential(apiKey))
            .GetChatClient(chatDeployment)
            .AsIChatClient();
        var keypointAgent = new RealtimeKeypointAgent(chatClient);
        var keypointThread = (RealtimeKeypointAgent.KeypointThread)keypointAgent.GetNewThread();

        var questionAnswerAgent = new RealtimeQuestionAnswerAgent(chatClient, memoryStore);

        Console.WriteLine("🎙️  Listening for speech. Press Ctrl+C to stop.");
        Console.WriteLine("📝 Transcription Agent: ACTIVE (Yellow)");
        Console.WriteLine("💡 Keypoint Agent: ACTIVE (Green)");
        Console.WriteLine("❓ Q&A Agent: ACTIVE (Magenta/Cyan)");
        Console.WriteLine();

        // Run five parallel tasks:
        // 1. Capture and broadcast transcripts to multiple channels
        // 2. Display transcripts and store in memory
        // 3. Extract and display keypoints
        // 4. Detect questions and answer them with web search
        var captureTask = CaptureAndBroadcastTranscriptsAsync(transcriptionAgent, displayChannel.Writer, keypointChannel.Writer, cancellationToken);
        var displayTask = DisplayAndStoreTranscriptsAsync(displayChannel.Reader, memoryStore, cancellationToken);
        var keypointTask = ExtractKeyPointsAsync(keypointChannel.Reader, keypointAgent, keypointThread, memoryStore, cancellationToken);
        var questionAnswerTask = questionAnswerAgent.RunAsync(cancellationToken);

        await Task.WhenAll(captureTask, displayTask, keypointTask, questionAnswerTask).ConfigureAwait(false);
    }

    private static async Task CaptureAndBroadcastTranscriptsAsync(
        RealtimeTranscriptionAgent transcriptionAgent,
        ChannelWriter<RealtimeTranscriptSegment> displayWriter,
        ChannelWriter<RealtimeTranscriptSegment> keypointWriter,
        CancellationToken cancellationToken)
    {
        try
        {
            await foreach (var segment in transcriptionAgent.StreamSegmentsAsync(cancellationToken).ConfigureAwait(false))
            {
                if (string.IsNullOrWhiteSpace(segment.Text))
                {
                    continue;
                }

                if (!segment.IsFinal)
                {
                    continue;
                }

                // Broadcast to both channels - this is FAST (no blocking)
                await displayWriter.WriteAsync(segment, cancellationToken).ConfigureAwait(false);
                await keypointWriter.WriteAsync(segment, cancellationToken).ConfigureAwait(false);
            }
        }
        finally
        {
            displayWriter.Complete();
            keypointWriter.Complete();
        }
    }

    private static async Task DisplayAndStoreTranscriptsAsync(
        ChannelReader<RealtimeTranscriptSegment> reader,
        TranscriptMemoryStore memoryStore,
        CancellationToken cancellationToken)
    {
        await foreach (var segment in reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
        {
            WriteTranscript(segment);
            await memoryStore.AddAsync(segment.Text, segment.Timestamp, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
    }

    private static async Task ExtractKeyPointsAsync(
        ChannelReader<RealtimeTranscriptSegment> reader,
        RealtimeKeypointAgent keypointAgent,
        RealtimeKeypointAgent.KeypointThread keypointThread,
        TranscriptMemoryStore memoryStore,
        CancellationToken cancellationToken)
    {
        // Buffer transcripts briefly before processing to reduce API calls
        var buffer = new System.Collections.Generic.List<string>();
        var lastProcessTime = DateTimeOffset.UtcNow;
        const int MinBufferSize = 2;
        var processingInterval = TimeSpan.FromSeconds(5);

        await foreach (var segment in reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
        {
            buffer.Add(segment.Text);

            var now = DateTimeOffset.UtcNow;
            bool shouldProcess = buffer.Count >= MinBufferSize || (now - lastProcessTime) >= processingInterval;

            if (shouldProcess && buffer.Count > 0)
            {
                string combinedText = string.Join(" ", buffer);
                buffer.Clear();
                lastProcessTime = now;

                // Fire-and-forget: Process keypoints in background to avoid blocking
                _ = Task.Run(async () =>
                {
                    try
                    {
                        var response = await keypointAgent.RunAsync(
                            new[] { new ChatMessage(ChatRole.User, combinedText) },
                            keypointThread,
                            options: null,
                            cancellationToken: CancellationToken.None).ConfigureAwait(false);

                        foreach (var message in response.Messages)
                        {
                            if (string.IsNullOrWhiteSpace(message.Text))
                            {
                                continue;
                            }

                            WriteKeyPoint(message.Text, message.CreatedAt);
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"[ERROR Keypoint] {ex.Message}");
                    }
                }, CancellationToken.None);
            }
        }

        // Process remaining buffer in background
        if (buffer.Count > 0)
        {
            string combinedText = string.Join(" ", buffer);
            _ = Task.Run(async () =>
            {
                try
                {
                    var response = await keypointAgent.RunAsync(
                        new[] { new ChatMessage(ChatRole.User, combinedText) },
                        keypointThread,
                        options: null,
                        cancellationToken: CancellationToken.None).ConfigureAwait(false);

                    foreach (var message in response.Messages)
                    {
                        if (!string.IsNullOrWhiteSpace(message.Text))
                        {
                            WriteKeyPoint(message.Text, message.CreatedAt);
                        }
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[ERROR Keypoint] {ex.Message}");
                }
            }, CancellationToken.None);
        }
    }

    private static readonly object s_consoleLock = new();

    private static void WriteTranscript(RealtimeTranscriptSegment segment)
    {
        lock (s_consoleLock)
        {
            var previousColor = Console.ForegroundColor;
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine($"[Transcript {segment.Timestamp:HH:mm:ss}] {segment.Text}");
            Console.ForegroundColor = previousColor;
        }
    }

    private static void WriteKeyPoint(string keyPoint, DateTimeOffset? createdAt)
    {
        lock (s_consoleLock)
        {
            var previousColor = Console.ForegroundColor;
            Console.ForegroundColor = ConsoleColor.Green;
            var timestamp = createdAt ?? DateTimeOffset.UtcNow;
            Console.WriteLine($"    💡 [Key Point {timestamp:HH:mm:ss}] {keyPoint}");
            Console.ForegroundColor = previousColor;
        }
    }

    public static void WriteQuestionAnswer(string question, string answer)
    {
        lock (s_consoleLock)
        {
            var previousColor = Console.ForegroundColor;
            Console.ForegroundColor = ConsoleColor.Magenta;
            Console.WriteLine($"\n    ❓ [Question] {question}");
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine($"    💬 [Answer] {answer}");
            Console.ResetColor();
        }
    }
}
