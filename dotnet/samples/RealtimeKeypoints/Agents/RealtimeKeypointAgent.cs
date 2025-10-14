// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using RealtimeKeypoints.Realtime;

namespace RealtimeKeypoints.Agents;

/// <summary>
/// Agent that converts streaming transcript segments into concise real-time key points.
/// </summary>
public sealed class RealtimeKeypointAgent : AIAgent
{
    private const string DefaultSystemPrompt = "You are a diligent meeting assistant that extracts concise, actionable" +
        " key points from a live transcript. Focus on findings, decisions, risks, and open questions." +
        " Avoid speculation. Do not repeat key points that were already announced.";

    private static readonly char[] s_bulletPrefixes = ['-', '*', '•', '+'];
    private static readonly string[] s_noNewPointTokens =
    [
        "no new points",
        "no_new_points",
        "no additional key points",
        "no new key points",
        "nothing new"
    ];

    private readonly IChatClient _chatClient;
    private readonly string _systemPrompt;
    private readonly int _maxTranscriptCharacters;

    public RealtimeKeypointAgent(IChatClient chatClient, string? systemPrompt = null, int maxTranscriptCharacters = 6000)
    {
        this._chatClient = chatClient ?? throw new ArgumentNullException(nameof(chatClient));
        this._systemPrompt = string.IsNullOrWhiteSpace(systemPrompt) ? DefaultSystemPrompt : systemPrompt;
        this._maxTranscriptCharacters = maxTranscriptCharacters > 0
            ? maxTranscriptCharacters
            : throw new ArgumentOutOfRangeException(nameof(maxTranscriptCharacters));
    }

    /// <summary>
    /// Consumes transcript segments and emits newly discovered key points.
    /// </summary>
    public async IAsyncEnumerable<string> StreamKeyPointsAsync(
        IAsyncEnumerable<RealtimeTranscriptSegment> transcriptSegments,
        KeypointThread? thread = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        thread ??= new KeypointThread(this._maxTranscriptCharacters);

        await foreach (var segment in transcriptSegments.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            if (string.IsNullOrWhiteSpace(segment.Text))
            {
                continue;
            }

            // Only trigger summaries when we see final segments to reduce duplicate calls.
            if (!segment.IsFinal && segment.Text.Length < 24)
            {
                continue;
            }

            var response = await this.RunAsync([
                new ChatMessage(ChatRole.User, segment.Text)
            ], thread, null, cancellationToken).ConfigureAwait(false);

            foreach (var message in response.Messages)
            {
                if (!string.IsNullOrWhiteSpace(message.Text))
                {
                    yield return message.Text;
                }
            }
        }
    }

    public override AgentThread GetNewThread() => new KeypointThread(this._maxTranscriptCharacters);

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new KeypointThread(serializedThread, jsonSerializerOptions, this._maxTranscriptCharacters);

    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var keypointThread = thread as KeypointThread ?? new KeypointThread(this._maxTranscriptCharacters);
        var inputMessages = messages as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        if (inputMessages.Count == 0)
        {
            return new AgentRunResponse(Array.Empty<ChatMessage>())
            {
                AgentId = this.Id
            };
        }

        await NotifyThreadOfNewMessagesAsync(keypointThread, inputMessages, cancellationToken).ConfigureAwait(false);

        List<ChatMessage> responseMessages = [];

        foreach (var message in inputMessages)
        {
            string text = message.Text;
            if (string.IsNullOrWhiteSpace(text))
            {
                continue;
            }

            IReadOnlyList<string> newPoints = await this.ExtractKeyPointsAsync(text, keypointThread, cancellationToken).ConfigureAwait(false);
            foreach (var keyPoint in newPoints)
            {
                var keyPointMessage = new ChatMessage(ChatRole.Assistant, keyPoint)
                {
                    CreatedAt = DateTimeOffset.UtcNow
                };
                responseMessages.Add(keyPointMessage);
            }
        }

        if (responseMessages.Count > 0)
        {
            await NotifyThreadOfNewMessagesAsync(keypointThread, responseMessages, cancellationToken).ConfigureAwait(false);
        }

        return new AgentRunResponse(responseMessages)
        {
            AgentId = this.Id
        };
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var response = await this.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);
        foreach (var message in response.Messages)
        {
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, message.Text)
            {
                AgentId = this.Id,
                CreatedAt = message.CreatedAt,
                MessageId = message.MessageId
            };
        }
    }

    private async Task<IReadOnlyList<string>> ExtractKeyPointsAsync(string transcriptChunk, KeypointThread thread, CancellationToken cancellationToken)
    {
        thread.AppendTranscript(transcriptChunk);

        string transcriptContext = thread.TranscriptContext;
        if (string.IsNullOrWhiteSpace(transcriptContext))
        {
            return Array.Empty<string>();
        }

        var promptMessages = new List<ChatMessage>
        {
            new(ChatRole.System, this._systemPrompt)
        };

        if (thread.KeyPoints.Count > 0)
        {
            var knownBuilder = new StringBuilder();
            foreach (var point in thread.KeyPoints)
            {
                knownBuilder.Append("- ").AppendLine(point);
            }

            promptMessages.Add(new ChatMessage(ChatRole.User, $"Key points already shared (do not repeat):{Environment.NewLine}{knownBuilder}"));
        }

        promptMessages.Add(new ChatMessage(ChatRole.User, $"Latest transcript excerpt:{Environment.NewLine}{transcriptChunk}"));

        if (!string.Equals(transcriptContext, transcriptChunk, StringComparison.Ordinal))
        {
            promptMessages.Add(new ChatMessage(ChatRole.User, $"Rolling transcript window (oldest to newest):{Environment.NewLine}{transcriptContext}"));
        }

        promptMessages.Add(new ChatMessage(ChatRole.User, "List any new decisions, action items, or notable facts introduced in this excerpt. " +
            "Respond only with bullet lines starting with '-'. If there is nothing new, respond with 'NO_NEW_POINTS'."));

        ChatResponse chatResponse = await this._chatClient.GetResponseAsync(promptMessages, options: null, cancellationToken).ConfigureAwait(false);
        string responseText = chatResponse.Text ?? string.Empty;

        if (string.IsNullOrWhiteSpace(responseText))
        {
            return Array.Empty<string>();
        }

        List<string> newKeyPoints = [];
        foreach (var keyPoint in ParseKeyPoints(responseText))
        {
            if (thread.TryAddKeyPoint(keyPoint))
            {
                newKeyPoints.Add(keyPoint);
            }
        }

        return newKeyPoints;
    }

    private static IEnumerable<string> ParseKeyPoints(string responseText)
    {
        if (string.IsNullOrWhiteSpace(responseText))
        {
            yield break;
        }

        string normalized = responseText.Trim();
        if (s_noNewPointTokens.Any(token => normalized.Contains(token, StringComparison.OrdinalIgnoreCase)))
        {
            yield break;
        }

        using var reader = new StringReader(normalized);
        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            line = line.Trim();
            if (line.Length == 0)
            {
                continue;
            }

            if (s_noNewPointTokens.Any(token => line.Equals(token, StringComparison.OrdinalIgnoreCase)))
            {
                yield break;
            }

            line = TrimPrefix(line);
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            yield return line.TrimEnd('.');
        }
    }

    private static string TrimPrefix(string value)
    {
        value = value.TrimStart();
        if (value.Length == 0)
        {
            return value;
        }

        if (char.IsDigit(value[0]))
        {
            int index = 0;
            while (index < value.Length && (char.IsDigit(value[index]) || value[index] == '.' || char.IsWhiteSpace(value[index])))
            {
                index++;
            }

            value = value[index..].TrimStart();
        }

        if (value.Length > 0 && s_bulletPrefixes.Contains(value[0]))
        {
            value = value[1..].TrimStart();
        }

        if (value.StartsWith("-", StringComparison.Ordinal))
        {
            value = value[1..].TrimStart();
        }

        return value;
    }

    /// <summary>
    /// Thread state that maintains rolling transcript context and previously emitted key points.
    /// </summary>
    public sealed class KeypointThread : InMemoryAgentThread
    {
        private readonly Queue<string> _transcriptWindow = new();
        private readonly List<string> _keyPoints = [];
        private readonly HashSet<string> _keyPointSet = new(StringComparer.OrdinalIgnoreCase);
        private readonly int _maxTranscriptCharacters;
        private int _transcriptCharacterCount;

        public KeypointThread(int maxTranscriptCharacters = 6000)
        {
            this._maxTranscriptCharacters = maxTranscriptCharacters;
        }

        public KeypointThread(JsonElement serializedThread, JsonSerializerOptions? options = null, int maxTranscriptCharacters = 6000)
            : base(serializedThread, options)
        {
            this._maxTranscriptCharacters = maxTranscriptCharacters;
        }

        public IReadOnlyList<string> KeyPoints => this._keyPoints;

        public string TranscriptContext => string.Join(Environment.NewLine, this._transcriptWindow);

        public void AppendTranscript(string transcriptChunk)
        {
            if (string.IsNullOrWhiteSpace(transcriptChunk))
            {
                return;
            }

            this._transcriptWindow.Enqueue(transcriptChunk.Trim());
            this._transcriptCharacterCount += transcriptChunk.Length;

            while (this._transcriptCharacterCount > this._maxTranscriptCharacters && this._transcriptWindow.Count > 0)
            {
                string removed = this._transcriptWindow.Dequeue();
                this._transcriptCharacterCount -= removed.Length;
            }
        }

        public bool TryAddKeyPoint(string keyPoint)
        {
            if (string.IsNullOrWhiteSpace(keyPoint))
            {
                return false;
            }

            if (!this._keyPointSet.Add(keyPoint.Trim()))
            {
                return false;
            }

            this._keyPoints.Add(keyPoint.Trim());
            return true;
        }
    }
}
