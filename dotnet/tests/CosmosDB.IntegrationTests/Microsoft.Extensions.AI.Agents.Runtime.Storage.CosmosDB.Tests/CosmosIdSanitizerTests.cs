// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

public class CosmosIdSanitizerTests
{
    [Fact]
    public void Sanitize_WithValidInputNoSpecialChars_ReturnsOriginalString()
    {
        // Arrange
        const string Input = "ValidId123";

        // Act
        string result = CosmosIdSanitizer.Sanitize(Input);

        // Assert
        Assert.Equal(Input, result);
    }

    [Fact]
    public void Sanitize_WithEmptyString_ReturnsEmptyString()
    {
        // Arrange
        const string Input = "";

        // Act
        string result = CosmosIdSanitizer.Sanitize(Input);

        // Assert
        Assert.Equal(Input, result);
    }

    [Theory]
    [InlineData("/", "~0")]
    [InlineData("\\", "~1")]
    [InlineData("?", "~2")]
    [InlineData("#", "~3")]
    [InlineData("_", "~4")]
    [InlineData("~", "~5")]
    public void Sanitize_WithSingleSpecialChar_ReturnsCorrectEscapeSequence(string input, string expected)
    {
        // Act
        string result = CosmosIdSanitizer.Sanitize(input);

        // Assert
        Assert.Equal(expected, result);
    }

    [Fact]
    public void Sanitize_WithMultipleSpecialChars_ReturnsCorrectEscapeSequences()
    {
        // Arrange
        const string Input = "test/path\\file?query#fragment_underscore~tilde";
        const string Expected = "test~0path~1file~2query~3fragment~4underscore~5tilde";

        // Act
        string result = CosmosIdSanitizer.Sanitize(Input);

        // Assert
        Assert.Equal(Expected, result);
    }

    [Fact]
    public void Sanitize_WithMixedValidAndSpecialChars_ReturnsCorrectResult()
    {
        // Arrange
        const string Input = "user/123";
        const string Expected = "user~0123";

        // Act
        string result = CosmosIdSanitizer.Sanitize(Input);

        // Assert
        Assert.Equal(Expected, result);
    }

    [Fact]
    public void Unsanitize_WithValidInputNoEscapeChars_ReturnsOriginalString()
    {
        // Arrange
        const string Input = "ValidId123";

        // Act
        string result = CosmosIdSanitizer.Unsanitize(Input);

        // Assert
        Assert.Equal(Input, result);
    }

    [Fact]
    public void Unsanitize_WithEmptyString_ReturnsEmptyString()
    {
        // Arrange
        const string Input = "";

        // Act
        string result = CosmosIdSanitizer.Unsanitize(Input);

        // Assert
        Assert.Equal(Input, result);
    }

    [Theory]
    [InlineData("~0", "/")]
    [InlineData("~1", "\\")]
    [InlineData("~2", "?")]
    [InlineData("~3", "#")]
    [InlineData("~4", "_")]
    [InlineData("~5", "~")]
    public void Unsanitize_WithSingleEscapeSequence_ReturnsCorrectChar(string input, string expected)
    {
        // Act
        string result = CosmosIdSanitizer.Unsanitize(input);

        // Assert
        Assert.Equal(expected, result);
    }

    [Fact]
    public void Unsanitize_WithMultipleEscapeSequences_ReturnsCorrectResult()
    {
        // Arrange
        const string Input = "test~0path~1file~2query~3fragment~4underscore~5tilde";
        const string Expected = "test/path\\file?query#fragment_underscore~tilde";

        // Act
        string result = CosmosIdSanitizer.Unsanitize(Input);

        // Assert
        Assert.Equal(Expected, result);
    }

    [Fact]
    public void Unsanitize_WithMixedValidAndEscapeChars_ReturnsCorrectResult()
    {
        // Arrange
        const string Input = "user~0123";
        const string Expected = "user/123";

        // Act
        string result = CosmosIdSanitizer.Unsanitize(Input);

        // Assert
        Assert.Equal(Expected, result);
    }

    [Theory]
    [InlineData("~6")]
    [InlineData("~A")]
    [InlineData("~z")]
    public void Unsanitize_WithInvalidEscapeSequence_ThrowsArgumentException(string input)
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => CosmosIdSanitizer.Unsanitize(input));
        Assert.Contains("Input is not in a valid format: Encountered unsupported escape sequence", exception.Message);
    }

    [Fact]
    public void SanitizeUnsanitize_RoundTrip_ReturnsOriginalString()
    {
        // Arrange
        const string Original = "user/path\\to?file#with_underscore~and~tildes";

        // Act
        string sanitized = CosmosIdSanitizer.Sanitize(Original);
        string unsanitized = CosmosIdSanitizer.Unsanitize(sanitized);

        // Assert
        Assert.Equal(Original, unsanitized);
    }

    [Theory]
    [InlineData("")]
    [InlineData("a")]
    [InlineData("abc")]
    [InlineData("simple-text")]
    [InlineData("user123")]
    [InlineData("user/path")]
    [InlineData("/\\?#_~")]
    [InlineData("complex/path\\with?query#fragment_underscore~tilde")]
    public void SanitizeUnsanitize_RoundTripProperty_AlwaysReturnsOriginal(string original)
    {
        // Act
        string sanitized = CosmosIdSanitizer.Sanitize(original);
        string unsanitized = CosmosIdSanitizer.Unsanitize(sanitized);

        // Assert
        Assert.Equal(original, unsanitized);
    }

    [Fact]
    public void Sanitize_WithLongString_HandlesCorrectly()
    {
        // Arrange
        var input = new string('a', 1000) + "/" + new string('b', 1000) + "\\" + new string('c', 1000);

        // Act
        string result = CosmosIdSanitizer.Sanitize(input);

        // Assert
        Assert.Contains("~0", result);
        Assert.Contains("~1", result);
        Assert.Equal(3004, result.Length); // Original 3002 chars + 2 escape chars
    }

    [Fact]
    public void Unsanitize_WithLongString_HandlesCorrectly()
    {
        // Arrange
        var input = new string('a', 1000) + "~0" + new string('b', 1000) + "~1" + new string('c', 1000);

        // Act
        string result = CosmosIdSanitizer.Unsanitize(input);

        // Assert
        Assert.Contains("/", result);
        Assert.Contains("\\", result);
        Assert.Equal(3002, result.Length); // 3004 chars - 2 escape chars
    }

    [Fact]
    public void SeparatorChar_HasCorrectValue() =>
        // Assert
        Assert.Equal('_', CosmosIdSanitizer.SeparatorChar);

    [Fact]
    public void Sanitize_WithOnlySeparatorChar_EscapesCorrectly()
    {
        // Arrange
        const string Input = "_";

        // Act
        string result = CosmosIdSanitizer.Sanitize(Input);

        // Assert
        Assert.Equal("~4", result);
    }

    [Fact]
    public void Sanitize_WithConsecutiveSpecialChars_HandlesCorrectly()
    {
        // Arrange
        const string Input = "//\\\\??##__~~";
        const string Expected = "~0~0~1~1~2~2~3~3~4~4~5~5";

        // Act
        string result = CosmosIdSanitizer.Sanitize(Input);

        // Assert
        Assert.Equal(Expected, result);
    }

    [Fact]
    public void Unsanitize_WithConsecutiveEscapeSequences_HandlesCorrectly()
    {
        // Arrange
        const string Input = "~0~0~1~1~2~2~3~3~4~4~5~5";
        const string Expected = "//\\\\??##__~~";

        // Act
        string result = CosmosIdSanitizer.Unsanitize(Input);

        // Assert
        Assert.Equal(Expected, result);
    }
}
