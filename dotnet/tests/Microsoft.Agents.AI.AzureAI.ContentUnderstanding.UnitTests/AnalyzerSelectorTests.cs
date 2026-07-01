// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 3 / dev plan task 3.3 — media type → analyzer mapping.
/// </summary>
public sealed class AnalyzerSelectorTests
{
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

    [Fact]
    public void Select_ExplicitOverrideWinsOverAuto()
        => Assert.Equal("my-custom-analyzer", AnalyzerSelector.Select("audio/mpeg", "my-custom-analyzer"));

    [Fact]
    public void Select_EmptyOverrideFallsThroughToAuto()
        => Assert.Equal(AnalyzerSelector.AudioAnalyzer, AnalyzerSelector.Select("audio/mpeg", string.Empty));

    [Fact]
    public void Select_WhitespaceOverrideFallsThroughToAuto()
        => Assert.Equal(AnalyzerSelector.AudioAnalyzer, AnalyzerSelector.Select("audio/mpeg", "   "));
}
