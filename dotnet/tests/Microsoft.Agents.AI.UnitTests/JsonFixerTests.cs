// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1118, RCS1192

using Xunit;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Tests for <see cref="JsonFixer"/>.
/// </summary>
public class JsonFixerTests
{
    // ---------- Markdown Fence Stripping ----------

    [Fact]
    public void TryStripMarkdownFences_NoFence_ReturnsFalse()
    {
        string text = @"{""key"": ""value""}";
        string original = text;
        bool result = JsonFixer.TryStripMarkdownFences(ref text);
        Assert.False(result);
        Assert.Equal(original, text);
    }

    [Fact]
    public void TryStripMarkdownFences_WithFence_RemovesFence()
    {
        string text = "```json\n{\"key\": \"value\"}\n```";
        string expected = @"{""key"": ""value""}";
        bool result = JsonFixer.TryStripMarkdownFences(ref text);
        Assert.True(result);
        Assert.Equal(expected, text);
    }

    [Fact]
    public void TryStripMarkdownFences_NoClosingFence_StripsOpeningFence()
    {
        string text = "```json\n{\"key\": \"value\"}";
        string expected = @"{""key"": ""value""}";
        bool result = JsonFixer.TryStripMarkdownFences(ref text);
        Assert.True(result);
        Assert.Equal(expected, text);
    }

    // ---------- Trailing Comma Fixing ----------

    [Fact]
    public void TryFixTrailingCommas_NoTrailingComma_ReturnsFalse()
    {
        string text = @"{""a"": 1, ""b"": 2}";
        string original = text;
        bool result = JsonFixer.TryFixTrailingCommas(ref text);
        Assert.False(result);
        Assert.Equal(original, text);
    }

    [Fact]
    public void TryFixTrailingCommas_BeforeClosingBrace_RemovesComma()
    {
        string text = @"{""a"": 1,}";
        string expected = @"{""a"": 1}";
        bool result = JsonFixer.TryFixTrailingCommas(ref text);
        Assert.True(result);
        Assert.Equal(expected, text);
    }

    [Fact]
    public void TryFixTrailingCommas_BeforeClosingBracket_RemovesComma()
    {
        string text = @"[1, 2,]";
        string expected = @"[1, 2]";
        bool result = JsonFixer.TryFixTrailingCommas(ref text);
        Assert.True(result);
        Assert.Equal(expected, text);
    }

    // ---------- Truncated JSON Fixing ----------

    [Fact]
    public void TryFixTruncatedJson_CompleteJson_ReturnsFalse()
    {
        string text = @"{""a"": 1, ""b"": [1, 2, 3]}";
        string original = text;
        bool result = JsonFixer.TryFixTruncatedJson(ref text);
        Assert.False(result);
        Assert.Equal(original, text);
    }

    [Fact]
    public void TryFixTruncatedJson_MissingClosingBrace_AddsIt()
    {
        string text = @"{""a"": 1";
        string expected = @"{""a"": 1}";
        bool result = JsonFixer.TryFixTruncatedJson(ref text);
        Assert.True(result);
        Assert.Equal(expected, text);
    }

    [Fact]
    public void TryFixTruncatedJson_MissingBracketsAndBraces_AddsThem()
    {
        string text = @"{""a"": [1, 2";
        string expected = @"{""a"": [1, 2]}";
        bool result = JsonFixer.TryFixTruncatedJson(ref text);
        Assert.True(result);
        Assert.Equal(expected, text);
    }

    [Fact]
    public void TryFixTruncatedJson_UnclosedString_ClosesIt()
    {
        string text = @"{""a"": ""hello";
        string expected = @"{""a"": ""hello""}";
        bool result = JsonFixer.TryFixTruncatedJson(ref text);
        Assert.True(result);
        Assert.Equal(expected, text);
    }

    // ---------- Nested JSON Unstringifying ----------

    [Fact]
    public void TryUnstringifyNestedJson_ValidNestedJson_GetsInlined()
    {
        // Arrange
        string text = @"{""arguments"": ""{}""}";

        // Act
        bool result = JsonFixer.TryUnstringifyNestedJson(ref text);

        // Assert
        Assert.True(result);
        Assert.Equal(@"{""arguments"": {}}", text);
    }

    [Fact]
    public void TryUnstringifyNestedJson_InvalidJsonValue_LeftUntouched()
    {
        // Arrange
        string text = @"{""arguments"": ""not-valid-json""}";

        // Act
        bool result = JsonFixer.TryUnstringifyNestedJson(ref text);

        // Assert
        Assert.False(result);
    }

    // ---------- Combined TryFix ----------

    [Fact]
    public void TryFix_MarkdownFenceWithCommas_FixesBoth()
    {
        string text = "```json\n{\"a\": 1,}\n```";
        string expected = @"{""a"": 1}";
        bool result = JsonFixer.TryFix(text, out string? fixedText);
        Assert.True(result);
        Assert.NotNull(fixedText);
        Assert.Equal(expected, fixedText);
    }

    [Fact]
    public void TryFix_TruncatedWithFence_FixesBoth()
    {
        string text = "```json\n{\"a\": [1, 2";
        string expected = @"{""a"": [1, 2]}";
        bool result = JsonFixer.TryFix(text, out string? fixedText);
        Assert.True(result);
        Assert.NotNull(fixedText);
        Assert.Equal(expected, fixedText);
    }

    [Fact]
    public void TryFix_NullText_ReturnsFalse()
    {
        bool result = JsonFixer.TryFix(null, out string? fixedText);
        Assert.False(result);
        Assert.Null(fixedText);
    }

    [Fact]
    public void TryFix_EmptyText_ReturnsFalse()
    {
        bool result = JsonFixer.TryFix(string.Empty, out string? fixedText);
        Assert.False(result);
        Assert.Null(fixedText);
    }
}
