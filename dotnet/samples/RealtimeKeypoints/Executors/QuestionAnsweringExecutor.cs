// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Reflection;
using RealtimeKeypoints.Agents;
using RealtimeKeypoints.Memory;

namespace RealtimeKeypoints.Executors;

/// <summary>
/// Executor that runs in a continuous loop, polling the memory store for new transcripts.
/// When new transcripts are found, it detects questions and answers them using AI.
/// </summary>
internal sealed class QuestionAnsweringExecutor : ReflectingExecutor<QuestionAnsweringExecutor>, IMessageHandler<object>
{
    private readonly RealtimeQuestionAnswerAgent _questionAnswerAgent;
    private readonly TranscriptMemoryStore _memoryStore;

    public QuestionAnsweringExecutor(
        RealtimeQuestionAnswerAgent questionAnswerAgent,
        TranscriptMemoryStore memoryStore)
        : base("QuestionAnsweringExecutor")
    {
        this._questionAnswerAgent = questionAnswerAgent ?? throw new ArgumentNullException(nameof(questionAnswerAgent));
        this._memoryStore = memoryStore ?? throw new ArgumentNullException(nameof(memoryStore));
    }

    public async ValueTask HandleAsync(object message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        try
        {
            Console.WriteLine("❓ Q&A Agent: ACTIVE");
            DateTimeOffset lastProcessedTime = DateTimeOffset.MinValue;
            const int PollingIntervalMs = 2000;

            while (!cancellationToken.IsCancellationRequested)
            {
                try
                {
                    await Task.Delay(PollingIntervalMs, cancellationToken).ConfigureAwait(false);

                    var recentTranscripts = await this._memoryStore.GetRecentTranscriptsAsync(
                        TimeSpan.FromSeconds(45),
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

                    foreach (var transcript in newTranscripts)
                    {
                        _ = Task.Run(
                            async () =>
                            {
                                try
                                {
                                    await this._questionAnswerAgent.DetectAndAnswerQuestionsAsync(
                                        transcript,
                                        cancellationToken).ConfigureAwait(false);
                                }
                                catch (Exception taskEx)
                                {
                                    Console.WriteLine($"[ERROR Q&A] {taskEx.Message}");
                                }
                            },
                            cancellationToken);
                    }
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[ERROR Q&A] {ex.Message}");
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[ERROR Q&A Executor] {ex.Message}");
            throw;
        }
    }
}
