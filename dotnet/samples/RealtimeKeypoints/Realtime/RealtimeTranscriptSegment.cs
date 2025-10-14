// Copyright (c) Microsoft. All rights reserved.

namespace RealtimeKeypoints.Realtime;

/// <summary>
/// Represents a chunk of transcript text emitted by the realtime Azure OpenAI session.
/// </summary>
public sealed record RealtimeTranscriptSegment(string Text, DateTimeOffset Timestamp, bool IsFinal = false);
