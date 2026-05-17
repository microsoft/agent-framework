// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 8 — multi-segment audio/video coverage. The CU SDK's <see cref="LlmInputHelper"/>
/// already concatenates per-segment blocks; these tests pin that behavior end-to-end through
/// our renderer wrapper and the provider's injection path so an upstream regression cannot
/// silently break the multi-segment story without a failing test.
/// </summary>
public sealed class AnalysisRendererSegmentsTests
{
    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestCategoryExtraction::test_category_in_multi_segment_video
    // parity: python tests/cu/test_context_provider.py::TestOutputFiltering::test_page_markers_passed_through_to_llm_input
    public void Render_MultiSegmentVideo_EmitsTimeRangePerSegment_WithSeparators()
    {
        AnalysisResult result = SharedTestFixtures.MakeMultiSegmentVideoResult(segmentCount: 3, segmentDurationSec: 30);

        string rendered = AnalysisRenderer.Render(result, "demo.mp4", AnalysisSection.Markdown);

        // Three audioVisual blocks → three timeRange front-matter entries.
        int timeRangeCount = CountOccurrences(rendered, "timeRange:");
        Assert.Equal(3, timeRangeCount);

        // LlmInputHelper joins blocks with "\n\n*****\n\n" — verify two separators between three blocks.
        int separatorCount = CountOccurrences(rendered, "*****");
        Assert.Equal(2, separatorCount);

        // Each segment's markdown is present.
        Assert.Contains("## Segment 0", rendered, StringComparison.Ordinal);
        Assert.Contains("## Segment 1", rendered, StringComparison.Ordinal);
        Assert.Contains("## Segment 2", rendered, StringComparison.Ordinal);

        // Front-matter source repeats per block (one per segment).
        Assert.Equal(3, CountOccurrences(rendered, "source: demo.mp4"));
        Assert.Equal(3, CountOccurrences(rendered, "contentType: audioVisual"));
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestCategoryExtraction::test_category_included_single_segment (rendering-shape half)
    public void Render_SingleSegmentVideo_OmitsTimeRangeAndSeparators()
    {
        AnalysisResult result = SharedTestFixtures.MakeMultiSegmentVideoResult(segmentCount: 1, segmentDurationSec: 30);

        string rendered = AnalysisRenderer.Render(result, "short.mp4", AnalysisSection.Markdown);

        // Per LlmInputHelper, timeRange is only emitted when multiple AV contents are present.
        Assert.DoesNotContain("timeRange:", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("*****", rendered, StringComparison.Ordinal);
        Assert.Contains("## Segment 0", rendered, StringComparison.Ordinal);
        Assert.Contains("contentType: audioVisual", rendered, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetectionE2E::test_video_file_uses_video_analyzer (end-to-end injection)
    public async Task InvokingAsync_MultiSegmentVideo_InjectsAllSegmentsIntoMessages()
    {
        AnalysisResult videoResult = SharedTestFixtures.MakeMultiSegmentVideoResult(segmentCount: 3, segmentDurationSec: 30);
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "demo.mp4",
            new AnalysisOutcome(true, videoResult, "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = new(
            SharedTestFixtures.TestEndpoint,
            new FakeTokenCredential())
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
        };

        // Real video bytes aren't needed — DataContent.MediaType is honored when supplied.
        DataContent video = new(new byte[] { 0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70 }, "video/mp4")
        {
            Name = "demo.mp4",
        };
        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Summarize."), video]) } }),
            CancellationToken.None);

        Assert.Equal(1, analyzer.CallCount);
        Assert.Equal("prebuilt-videoSearch", analyzer.Calls[0].AnalyzerId);

        List<ChatMessage> messages = result.Messages!.ToList();
        ChatMessage systemNote = messages.First(m => m.Role == ChatRole.System);
        string injected = string.Concat(systemNote.Contents.OfType<TextContent>().Select(t => t.Text));

        // All three segments reach the agent context in one block.
        Assert.Contains("## Segment 0", injected, StringComparison.Ordinal);
        Assert.Contains("## Segment 1", injected, StringComparison.Ordinal);
        Assert.Contains("## Segment 2", injected, StringComparison.Ordinal);
        Assert.Equal(3, CountOccurrences(injected, "timeRange:"));
    }

    private static int CountOccurrences(string haystack, string needle)
    {
        int count = 0;
        int index = 0;
        while ((index = haystack.IndexOf(needle, index, StringComparison.Ordinal)) >= 0)
        {
            count++;
            index += needle.Length;
        }
        return count;
    }
}
