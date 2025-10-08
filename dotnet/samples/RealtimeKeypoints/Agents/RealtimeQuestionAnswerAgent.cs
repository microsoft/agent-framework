// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using RealtimeKeypoints.Memory;
using System.Collections.Concurrent;

namespace RealtimeKeypoints.Agents;

/// <summary>
/// Agent that detects questions from transcripts and answers them using AI.
/// Each question is processed in a separate background task to avoid blocking.
/// </summary>
public sealed class RealtimeQuestionAnswerAgent
{
    private readonly IChatClient _chatClient;
    private readonly TranscriptMemoryStore _memoryStore;
    private readonly ConcurrentDictionary<string, bool> _processedQuestions; // Track questions being processed

    public RealtimeQuestionAnswerAgent(IChatClient chatClient, TranscriptMemoryStore memoryStore)
    {
        this._chatClient = chatClient ?? throw new ArgumentNullException(nameof(chatClient));
        this._memoryStore = memoryStore ?? throw new ArgumentNullException(nameof(memoryStore));
        this._processedQuestions = new ConcurrentDictionary<string, bool>(StringComparer.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Monitors transcripts and answers questions in real-time.
    /// </summary>
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        Console.WriteLine("[Q&A Agent] Started");

        var lastProcessedTime = DateTimeOffset.MinValue;

        while (!cancellationToken.IsCancellationRequested)
        {
            await Task.Delay(2000, cancellationToken); // Check every 2 seconds

            var recentTranscripts = await this._memoryStore.GetRecentTranscriptsAsync(TimeSpan.FromSeconds(15), cancellationToken);

            if (recentTranscripts.Count == 0)
            {
                continue;
            }

            // Get only transcripts we haven't processed yet
            var newTranscripts = new List<string>();
            foreach (var t in recentTranscripts)
            {
                var timestamp = await this._memoryStore.GetTranscriptTimestampAsync(t, cancellationToken);
                if (timestamp > lastProcessedTime)
                {
                    newTranscripts.Add(t);
                }
            }

            if (newTranscripts.Count == 0)
            {
                continue;
            }

            // Update last processed time
            lastProcessedTime = await this._memoryStore.GetTranscriptTimestampAsync(recentTranscripts.Last(), cancellationToken);

            // Process each new transcript separately in background
            foreach (var transcript in newTranscripts)
            {
                string textToAnalyze = transcript;

                // Fire-and-forget: Spin off detection in background so we don't block the main loop
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await this.DetectAndAnswerQuestionsAsync(textToAnalyze, CancellationToken.None);
                    }
                    catch (Exception taskEx)
                    {
                        Console.WriteLine($"[ERROR Q&A] {taskEx.Message}");
                    }
                }, CancellationToken.None);
            }
        }
    }

    private async Task DetectAndAnswerQuestionsAsync(string text, CancellationToken cancellationToken)
    {
        try
        {
            // First, detect if there's a question using simple chat
            var detectionResponse = await this._chatClient.GetResponseAsync(
                new List<ChatMessage>
                {
                    new(ChatRole.User, $"Transcript: {text}")
                },
                new ChatOptions
                {
                    Instructions = "You are a question detector. Analyze the transcript and determine if it contains a question. If there is a question, extract it clearly and concisely. If there is NO question, respond with exactly: 'NO_QUESTION'. Return ONLY the question text or 'NO_QUESTION'."
                },
                cancellationToken: cancellationToken);

            string detectionResult = detectionResponse.ToString()?.Trim() ?? "";

            if (string.IsNullOrWhiteSpace(detectionResult) ||
                detectionResult.Equals("NO_QUESTION", StringComparison.OrdinalIgnoreCase) ||
                detectionResult.Contains("NO_QUESTION", StringComparison.OrdinalIgnoreCase))
            {
                return; // No question detected
            }

            // Question detected! Normalize it for deduplication
            string question = detectionResult;
            string questionKey = this.NormalizeQuestion(question);

            // Check if we're already processing this question (or a very similar one)
            if (!this._processedQuestions.TryAdd(questionKey, true))
            {
                return; // Duplicate question
            }

            try
            {
                // Spin off a separate task to answer the question (fire-and-forget)
                // This allows multiple questions to be answered in parallel
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await this.AnswerQuestionAsync(question, CancellationToken.None);
                    }
                    finally
                    {
                        // Remove from processed set after a delay to allow for deduplication window
                        await Task.Delay(TimeSpan.FromSeconds(30), CancellationToken.None);
                        this._processedQuestions.TryRemove(questionKey, out _);
                    }
                }, CancellationToken.None);
            }
            catch (Exception)
            {
                // If we fail to spin off the task, remove from processed set
                this._processedQuestions.TryRemove(questionKey, out _);
                throw;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[ERROR Q&A] {ex.Message}");
        }
    }

    private async Task AnswerQuestionAsync(string question, CancellationToken cancellationToken)
    {
        try
        {
            // Create a simple web search function tool
            var webSearchTool = AIFunctionFactory.Create(
                (string query) =>
                {
                    // Simulate web search - in real implementation, call Bing API or similar
                    return "[Simulated Web Search Results for: " + query + "]\n\n" +
                           "Recent information about " + query + ":\n" +
                           "• Latest updates and current developments\n" +
                           "• Recent news and announcements\n" +
                           "• Most up-to-date technical details and specifications\n\n" +
                           "Note: This is simulated search data. In production, this would call a real search API like Bing Search.";
                },
                "web_search",
                "Search the web for current information about a topic. Use this when the question asks about recent events, new releases, or information that changes over time.");

            // Use ChatClientAgent which handles tool calling automatically
            var agent = new ChatClientAgent(
                this._chatClient,
                instructions: "You are a helpful assistant that answers questions concisely and accurately. " +
                             "When a question requires current or recent information (like new releases, recent events, latest versions), " +
                             "use the web_search tool first to get up-to-date information, then provide a clear 2-3 sentence answer.",
                tools: [webSearchTool]);

            // Run the agent with the question
            var response = await agent.RunAsync(question, cancellationToken: cancellationToken);

            // Extract the answer from the response
            string answer = response.ToString()?.Trim() ?? "Unable to provide an answer.";

            // Display the Q&A using Program's static method for consistent formatting
            Program.WriteQuestionAnswer(question, answer);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[ERROR Q&A] {ex.Message}");
        }
    }

    private string NormalizeQuestion(string question)
    {
        // Normalize question for deduplication (uppercase, remove punctuation, trim)
        return new string(question.ToUpperInvariant()
            .Where(c => char.IsLetterOrDigit(c) || char.IsWhiteSpace(c))
            .ToArray())
            .Trim();
    }
}
