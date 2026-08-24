// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class StringExtensionsTests
{
    [Fact]
    public void TrimJsonWithDelimiter()
    {
        // Arrange
        const string Input =
            """
            ```json
            {
                "key": "value"
            }
            ```
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimJsonWithPadding()
    {
        // Arrange
        const string Input =
            """
                 
            ```json
            {
                "key": "value"
            }
            ```       
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimJsonWithUnqualifiedDelimiter()
    {
        // Arrange
        const string Input =
            """
            ```
            {
                "key": "value"
            }
            ```
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimJsonWithoutDelimiter()
    {
        // Arrange
        const string Input =
            """
            {
                "key": "value"
            }
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimJsonWithoutDelimiterWithPadding()
    {
        // Arrange
        const string Input =
            """

            {
                "key": "value"
            }    
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimMissingWithDelimiter()
    {
        // Arrange
        const string Input =
            """
            ```json
            ```
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void TrimJsonWithSurroundingText()
    {
        // Arrange
        const string Input =
            """
            Here is the result:
            ```json
            {
                "key": "value"
            }
            ```
            Additional explanation.
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimJsonWithSurroundingTextAndWindowsLineEndings()
    {
        // Arrange
        const string Input = "Here is the result:\r\n```json\r\n{\"key\":\"value\"}\r\n```\r\nAdditional explanation.";

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal("{\"key\":\"value\"}", result);
    }

    [Fact]
    public void TrimJsonUsesFirstFencedBlock()
    {
        // Arrange
        const string Input =
            """
            ```json
            {"key":"first"}
            ```
            ```json
            {"key":"second"}
            ```
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal("{\"key\":\"first\"}", result);
    }

    [Fact]
    public void TrimJsonPreservesNonWordCharacterAfterQualifier()
    {
        // Arrange
        const string Input = "```json\u0903{\"key\":\"value\"}```";

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal("\u0903{\"key\":\"value\"}", result);
    }

    [Fact]
    public void TrimJsonWithUnterminatedDelimiterReturnsTrimmedInput()
    {
        // Arrange
        string input = $"  ```json\n{new string(' ', 64)}X  ";

        // Act
        string result = input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(input.Trim(), result);
    }

    [Fact]
    public void TrimEmptyString()
    {
        // Act
        string result = string.Empty.TrimJsonDelimiter();

        // Assert
        Assert.Equal(string.Empty, result);
    }
}
