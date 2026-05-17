// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 3 / dev plan task 3.3 — media type → analyzer mapping.
/// </summary>
public sealed class AnalyzerSelectorTests
{
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetection::test_auto_detect_pdf
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetection::test_auto_detect_image
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetection::test_auto_detect_audio
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetection::test_auto_detect_video
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetectionE2E::test_audio_file_uses_audio_analyzer
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetectionE2E::test_video_file_uses_video_analyzer
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetectionE2E::test_pdf_file_uses_document_analyzer
    [Theory]
    [InlineData("application/pdf", "prebuilt-documentSearch")]
    [InlineData("image/png", "prebuilt-documentSearch")]
    [InlineData("image/jpeg", "prebuilt-documentSearch")]
    [InlineData("audio/mpeg", "prebuilt-audioSearch")]
    [InlineData("audio/wav", "prebuilt-audioSearch")]
    [InlineData("AUDIO/MPEG", "prebuilt-audioSearch")] // case insensitive
    [InlineData("video/mp4", "prebuilt-videoSearch")]
    [InlineData("Video/MP4", "prebuilt-videoSearch")]
    [InlineData("text/plain", "prebuilt-documentSearch")]
    [InlineData("", "prebuilt-documentSearch")]
    public void Select_BucketsByMediaType(string mediaType, string expected)
        => Assert.Equal(expected, AnalyzerSelector.Select(mediaType, explicitOverride: null));

    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetection::test_explicit_analyzer_always_wins
    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetectionE2E::test_explicit_override_ignores_media_type
    [Fact]
    public void Select_ExplicitOverrideWinsOverAuto()
        => Assert.Equal("my-custom-analyzer", AnalyzerSelector.Select("audio/mpeg", "my-custom-analyzer"));

    // parity: python tests/cu/test_context_provider.py::TestAnalyzerAutoDetection::test_auto_detect_unknown_falls_back_to_document
    [Fact]
    public void Select_EmptyOverrideFallsThroughToAuto()
        => Assert.Equal(AnalyzerSelector.AudioAnalyzer, AnalyzerSelector.Select("audio/mpeg", string.Empty));
}
