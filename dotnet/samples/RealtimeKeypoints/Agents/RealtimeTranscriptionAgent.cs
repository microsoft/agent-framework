// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using RealtimeKeypoints.Audio;
using RealtimeKeypoints.Realtime;

namespace RealtimeKeypoints.Agents;

/// <summary>
/// Agent that captures audio from the microphone and streams transcripts from Azure OpenAI GPT-Realtime.
/// </summary>
public sealed class RealtimeTranscriptionAgent : AIAgent
{
    private readonly AzureRealtimeClient _realtimeClient;
    private readonly Func<MicrophoneAudioSource> _audioSourceFactory;

    public RealtimeTranscriptionAgent(AzureRealtimeClient realtimeClient, Func<MicrophoneAudioSource>? audioSourceFactory = null)
    {
        this._realtimeClient = realtimeClient ?? throw new ArgumentNullException(nameof(realtimeClient));
        this._audioSourceFactory = audioSourceFactory ?? (() => new MicrophoneAudioSource());
    }

    /// <summary>
    /// Exposes the live stream of transcripts emitted by Azure OpenAI.
    /// </summary>
    public async IAsyncEnumerable<RealtimeTranscriptSegment> StreamSegmentsAsync(
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
    {
        await using var microphone = this._audioSourceFactory();
        ChannelReader<byte[]> audioChannel = microphone.Start(cancellationToken);

        await foreach (var segment in this._realtimeClient.StreamTranscriptsAsync(audioChannel, cancellationToken).ConfigureAwait(false))
        {
            yield return segment;
        }
    }

    public override AgentThread GetNewThread() => new RealtimeTranscriptionThread();

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new RealtimeTranscriptionThread(serializedThread, jsonSerializerOptions);

    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var transcriptionThread = thread as RealtimeTranscriptionThread ?? new RealtimeTranscriptionThread();
        var transcriptBuilder = new StringBuilder();

        await foreach (var update in this.RunStreamingAsync(messages, transcriptionThread, options, cancellationToken).ConfigureAwait(false))
        {
            transcriptBuilder.Append(update.Text);
        }

        var responseMessage = new ChatMessage(ChatRole.Assistant, transcriptBuilder.ToString());
        await NotifyThreadOfNewMessagesAsync(transcriptionThread, new[] { responseMessage }, cancellationToken).ConfigureAwait(false);

        return new AgentRunResponse(responseMessage)
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
        var transcriptionThread = thread as RealtimeTranscriptionThread ?? new RealtimeTranscriptionThread();
        var inputMessages = messages is IReadOnlyCollection<ChatMessage> collection ? collection : new List<ChatMessage>(messages);

        if (inputMessages.Count > 0)
        {
            await NotifyThreadOfNewMessagesAsync(transcriptionThread, inputMessages, cancellationToken).ConfigureAwait(false);
        }

        await foreach (var segment in this.StreamSegmentsAsync(cancellationToken).ConfigureAwait(false))
        {
            transcriptionThread.AppendSegment(segment);

            var chatMessage = new ChatMessage(ChatRole.Assistant, segment.Text)
            {
                CreatedAt = segment.Timestamp
            };

            await NotifyThreadOfNewMessagesAsync(transcriptionThread, new[] { chatMessage }, cancellationToken).ConfigureAwait(false);

            yield return new AgentRunResponseUpdate(ChatRole.Assistant, segment.Text)
            {
                CreatedAt = segment.Timestamp,
                AgentId = this.Id,
                MessageId = segment.Timestamp.ToUnixTimeMilliseconds().ToString()
            };
        }
    }

    private sealed class RealtimeTranscriptionThread : InMemoryAgentThread
    {
        private readonly List<RealtimeTranscriptSegment> _segments = [];

        public RealtimeTranscriptionThread()
        {
        }

        public RealtimeTranscriptionThread(JsonElement serializedThread, JsonSerializerOptions? options = null)
            : base(serializedThread, options)
        {
        }

        public IReadOnlyList<RealtimeTranscriptSegment> Segments => this._segments;

        public void AppendSegment(RealtimeTranscriptSegment segment)
        {
            this._segments.Add(segment);
        }
    }
}
