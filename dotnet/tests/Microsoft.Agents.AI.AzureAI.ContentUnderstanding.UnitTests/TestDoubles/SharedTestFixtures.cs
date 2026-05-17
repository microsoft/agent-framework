// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Shared fixtures for ContentUnderstandingContextProvider unit tests across phases. Phase 5
/// originally inlined these as private nested helpers; Phase 6 lifted them so multiple test
/// files (Phase 5 happy path, Phase 6 background continuation, Phase 7 tools, ...) can share.
/// </summary>
internal static class SharedTestFixtures
{
    public static readonly Uri TestEndpoint = new("https://contoso.cognitiveservices.azure.com/");

    public static byte[] LoadFixturePdf()
    {
        // Real %PDF- header bytes so DataContent's content-type detection / our MIME sniff are happy.
        return new byte[]
        {
            0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34, 0x0A, 0x25, 0xE2, 0xE3, 0xCF, 0xD3, 0x0A,
        };
    }

    public static AnalysisResult MakeInvoiceResult()
    {
        Dictionary<string, ContentField> fields = new(StringComparer.Ordinal)
        {
            ["VendorName"] = ContentUnderstandingModelFactory.ContentStringField(value: "CONTOSO LTD."),
            ["TotalDue"] = ContentUnderstandingModelFactory.ContentStringField(value: "$610.00"),
        };
        DocumentContent content = ContentUnderstandingModelFactory.DocumentContent(
            mimeType: "application/pdf",
            markdown: "CONTOSO LTD.\n\n# INVOICE\n\nTotal due: $610.00",
            fields: fields,
            startPageNumber: 1,
            endPageNumber: 1);
        return ContentUnderstandingModelFactory.AnalysisResult(contents: [content]);
    }

    /// <summary>
    /// Synthesizes an <see cref="AnalysisResult"/> shaped like the long-form audio/video output
    /// returned by <c>prebuilt-videoSearch</c>: a single result whose <c>Contents</c> list holds
    /// N <see cref="AudioVisualContent"/> blocks, each covering 30s, with distinct markdown.
    /// </summary>
    /// <remarks>
    /// Mirrors the SDK contract verified in Phase 8 analysis: CU returns one <c>AnalysisResult</c>
    /// with multiple <c>AudioVisualContent</c> entries (not multiple results). The renderer in
    /// <see cref="LlmInputHelper"/> emits <c>timeRange:</c> only when <c>avCount &gt; 1</c>.
    /// </remarks>
    public static AnalysisResult MakeMultiSegmentVideoResult(int segmentCount, int segmentDurationSec = 30)
    {
        AudioVisualContent[] segments = new AudioVisualContent[segmentCount];
        for (int i = 0; i < segmentCount; i++)
        {
            long startMs = (long)i * segmentDurationSec * 1000L;
            long endMs = (long)(i + 1) * segmentDurationSec * 1000L;
            segments[i] = ContentUnderstandingModelFactory.AudioVisualContent(
                mimeType: "video/mp4",
                markdown: $"## Segment {i}\n\nNarration for segment {i}.",
                startTimeMsValue: startMs,
                endTimeMsValue: endMs);
        }
        return ContentUnderstandingModelFactory.AnalysisResult(contents: segments);
    }
}

/// <summary>An <see cref="AgentSession"/> implementation that holds only the inherited StateBag.</summary>
internal sealed class AgentSessionFake : AgentSession
{
}

/// <summary>
/// A throw-only <see cref="AIAgent"/>; the provider's <see cref="AIContextProvider.InvokingContext"/>
/// constructor requires a non-null agent reference but never calls into it for unit tests.
/// </summary>
internal sealed class TestAIAgentStub : AIAgent
{
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) => throw new NotSupportedException();

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) => throw new NotSupportedException();

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
        AgentSession session,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default) => throw new NotSupportedException();

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default) => throw new NotSupportedException();

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(
        CancellationToken cancellationToken = default) => throw new NotSupportedException();
}
